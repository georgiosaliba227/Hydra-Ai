import Foundation
import Darwin

/// Manual answers stay on this device. No credentials, HealthKit records or goal API payloads are persisted here.
enum GoalProfileStoreError: LocalizedError {
    case consent, unavailable, corrupt, noProfile
    var errorDescription: String? {
        switch self {
        case .consent: "Choose to save your profile on this iPhone before continuing."
        case .unavailable: "The local goal profile is unavailable. Nothing will be overwritten. Unlock this iPhone and retry, or explicitly delete the saved profile."
        case .corrupt: "The saved goal profile could not be validated. Nothing will be overwritten. Explicitly delete it to start again."
        case .noProfile: "There is no saved goal profile to export for this connection."
        }
    }
}

@MainActor final class GoalProfileStore: ObservableObject {
    @Published private(set) var profile: GoalProfile?
    @Published private(set) var errorMessage: String?
    var canSave: Bool { scope != nil && !blocked }

    private let directory: URL
    private let scopeResolver: (APIConfiguration) throws -> UUID
    private var scope: UUID?
    private var blocked = false
    private static let maximumBytes = 16_384
    // UUIDv5(URL namespace, "HydraAI.goal-profiles-v1.on_device"). Backend
    // bindings use random UUIDv4 scopes. This separate local destination never
    // reads the credential registry and stays stable when backend settings change.
    private static let onDeviceScope = UUID(uuidString: "D4F00AF4-7D4A-5D09-8EFB-F253536B98B5")!
    private struct Saved: Codable {
        let version: Int
        let scope: UUID
        let profile: GoalProfile
    }

    init(directory: URL? = nil, scopeResolver: ((APIConfiguration) throws -> UUID)? = nil) {
        // Resolve the system-provided container prefix only. Injected paths must retain symlinks for rejection.
        self.directory = (directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .resolvingSymlinksInPath().appendingPathComponent("HydraAI/goal-profiles-v1", isDirectory: true)).standardizedFileURL
        self.scopeResolver = scopeResolver ?? CalibrationConnectionScope.resolve
    }

    func configure(_ configuration: APIConfiguration, now: Date = .now) {
        profile = nil; errorMessage = nil; scope = nil; blocked = false
        guard !configuration.offline,
              configuration.onDevice || (try? configuration.validatedURL()) != nil else { return }
        do {
            if configuration.onDevice {
                scope = Self.onDeviceScope
            } else {
                scope = try scopeResolver(configuration)
            }
            try reload(now: now)
        } catch { fail(error) }
    }

    func reload(now: Date = .now) throws {
        do {
            guard let scope else { throw GoalProfileStoreError.unavailable }
            try checkDirectories()
            guard let saved = try read(scope, now: now) else {
                profile = nil; blocked = false; errorMessage = nil
                return
            }
            profile = saved; blocked = false; errorMessage = nil
        } catch { fail(error); throw error }
    }

    func save(_ profile: GoalProfile, consent: Bool, now: Date = .now) throws {
        guard consent else { errorMessage = GoalProfileStoreError.consent.localizedDescription; throw GoalProfileStoreError.consent }
        guard canSave else { throw GoalProfileStoreError.unavailable }
        do { try GoalProfileValidation.validate(profile, now: now) }
        catch { errorMessage = error.localizedDescription; throw error }
        try reload(now: now) // Revalidate the disk record before replacing it, including dangling links.
        guard let scope else { throw GoalProfileStoreError.unavailable }
        do {
            try persist(Saved(version: 1, scope: scope, profile: profile))
            self.profile = profile; errorMessage = nil
        } catch { fail(error); throw GoalProfileStoreError.unavailable }
    }

    /// Explicit recovery can remove an unreadable file or unlink a symlink without following its target.
    func deleteCurrent() throws {
        do {
            guard let scope else { throw GoalProfileStoreError.unavailable }
            try checkDirectories()
            let file = file(scope)
            if try attributes(file) != nil { try FileManager.default.removeItem(at: file) }
            profile = nil; errorMessage = nil; blocked = false
        } catch { fail(error); throw GoalProfileStoreError.unavailable }
    }

    /// Removes every connection's profile, including corrupt envelopes, even when no backend is configured.
    func deleteAll() throws {
        do {
            try checkDirectories(includeDirectory: false)
            if try attributes(directory) != nil { try FileManager.default.removeItem(at: directory) }
            profile = nil; errorMessage = nil; blocked = false
        } catch { fail(error); throw GoalProfileStoreError.unavailable }
    }

    /// Only call after the user explicitly requests local export; this contains their manual profile answers.
    func exportData(now: Date = .now) throws -> Data {
        guard canSave else { throw GoalProfileStoreError.unavailable }
        try reload(now: now)
        guard let profile else { throw GoalProfileStoreError.noProfile }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(profile)
    }

    private func file(_ scope: UUID) -> URL { directory.appendingPathComponent(scope.uuidString + ".json") }

    /// lstat sees dangling symbolic links, unlike fileExists. Missing ancestors are allowed only for creation.
    private func attributes(_ url: URL) throws -> stat? {
        var value = stat()
        guard lstat(url.path, &value) == 0 else {
            if errno == ENOENT { return nil }
            throw GoalProfileStoreError.unavailable
        }
        return value
    }

    private func checkDirectories(includeDirectory: Bool = true) throws {
        guard directory.isFileURL, directory.path.hasPrefix("/") else { throw GoalProfileStoreError.unavailable }
        let components = directory.pathComponents
        let checked = includeDirectory ? components : Array(components.dropLast())
        var current = URL(fileURLWithPath: "/", isDirectory: true)
        for component in checked {
            if component != "/" { current.appendPathComponent(component, isDirectory: true) }
            if let node = try attributes(current) {
                guard node.st_mode & mode_t(S_IFMT) == mode_t(S_IFDIR) else { throw GoalProfileStoreError.unavailable }
            }
        }
    }

    private func read(_ scope: UUID, now: Date) throws -> GoalProfile? {
        let file = file(scope)
        guard let node = try attributes(file) else { return nil }
        guard node.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), node.st_size <= Self.maximumBytes else { throw GoalProfileStoreError.corrupt }
        // O_NOFOLLOW also rejects a final-component symlink swapped in after lstat.
        let descriptor = open(file.path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw GoalProfileStoreError.unavailable }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              opened.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), opened.st_size <= Self.maximumBytes else { throw GoalProfileStoreError.corrupt }
        let data = try handle.read(upToCount: Self.maximumBytes + 1) ?? Data()
        guard data.count <= Self.maximumBytes else { throw GoalProfileStoreError.corrupt }
        do {
            let object = try JSONSerialization.jsonObject(with: data)
            guard let envelope = object as? [String: Any], Set(envelope.keys) == ["version", "scope", "profile"],
                  let fields = envelope["profile"] as? [String: Any],
                  Set(fields.keys).isSubset(of: ["birthDate", "ageYears", "referenceGroup", "eligibility", "heightCm", "weightKg", "supplements"]) else { throw GoalProfileStoreError.corrupt }
            let saved = try JSONDecoder().decode(Saved.self, from: data)
            guard saved.version == 1, saved.scope == scope else { throw GoalProfileStoreError.corrupt }
            try GoalProfileValidation.validate(saved.profile, now: now)
            return saved.profile
        } catch { throw GoalProfileStoreError.corrupt }
    }

    private func persist(_ saved: Saved) throws {
        try checkDirectories()
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        try checkDirectories()
        try manager.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: directory.path)
        var excluded = URLResourceValues(); excluded.isExcludedFromBackup = true
        var folder = directory; try folder.setResourceValues(excluded)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(saved)
        guard data.count <= Self.maximumBytes else { throw GoalProfileStoreError.corrupt }
        var temporary = directory.appendingPathComponent(".\(UUID().uuidString).tmp")
        defer { try? manager.removeItem(at: temporary) }
        // Set every privacy attribute before publication, so attribute failures retain the old complete file.
        try data.write(to: temporary, options: [.withoutOverwriting, .completeFileProtection])
        try manager.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: temporary.path)
        try temporary.setResourceValues(excluded)
        try checkDirectories()
        if let node = try attributes(file(saved.scope)) {
            guard node.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG) else { throw GoalProfileStoreError.corrupt }
        }
        // Same-directory rename publishes a fully protected replacement atomically; it never follows a target link.
        guard rename(temporary.path, file(saved.scope).path) == 0 else { throw GoalProfileStoreError.unavailable }
    }

    private func fail(_ error: Error) {
        blocked = true
        errorMessage = ((error as? GoalProfileStoreError) ?? .unavailable).localizedDescription
        // Preserve the last valid profile in memory and the original file as evidence on failure.
    }
}
