import Foundation
import Darwin

/// A separate signed app sandbox is the only supported demo destination.
enum DemoAccount {
    static let bundleIdentifier = "com.georgiosaliba.hydraai.demo"
    static var isActive: Bool { permits(bundleIdentifier: Bundle.main.bundleIdentifier) }
    static func permits(bundleIdentifier: String?) -> Bool { bundleIdentifier == self.bundleIdentifier }
}

enum DemoAccountError: LocalizedError {
    case wrongBundle, invalidAnchor, marker, existingData, busy, clockRollback
    var errorDescription: String? {
        switch self {
        case .wrongBundle: "Simulated records are available only in Hydra Demo."
        case .invalidAnchor: "The demo date or timezone is unavailable."
        case .marker: "The demo marker is unavailable or invalid. No records were reset."
        case .existingData: "Unrecognized local data exists without a valid demo initialization. Nothing was replaced."
        case .busy: "Demo preparation is already running."
        case .clockRollback: "The clock is earlier than the saved demo anchor. Restore the clock to resume preparation safely."
        }
    }
}

/// Fictional, manually logged fixtures; these are neither health measurements nor model predictions.
struct DemoSeedPlan {
    struct Entry { let id: UUID; let request: CreateBeverageRequest }
    let entries: [Entry]
    let dailyGoalMl: Int
    let profile: GoalProfile

    static func make(now: Date, zone: TimeZone) throws -> Self {
        guard now.timeIntervalSince1970.isFinite,
              (947_894_400...253_400_000_000).contains(now.timeIntervalSince1970),
              Set(TimeZone.knownTimeZoneIdentifiers).union(["UTC", "GMT"]).contains(zone.identifier) else { throw DemoAccountError.invalidAnchor }
        // LocalBeverageService persists whole seconds. Normalize before building requests,
        // including the first run, so a resumed idempotency digest is byte-for-byte identical.
        let anchor = Date(timeIntervalSince1970: now.timeIntervalSince1970.rounded(.down))
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone
        let start = calendar.startOfDay(for: anchor)
        var entries: [Entry] = []
        let categories = ["water", "coffee", "water", "tea", "milk", "water"]
        let hours = [7, 9, 11, 13, 16, 19]
        for offset in -13...0 {
            guard let day = calendar.date(byAdding: .day, value: offset, to: start) else { throw DemoAccountError.invalidAnchor }
            let volumes = offset == 0 ? [500, 250, 500, 250, 250, 500] :
                [500, 200 + ((offset + 13) % 3) * 50, 500, 250, 250, 500 + ((offset + 13) % 4) * 250]
            for index in categories.indices {
                guard let scheduled = calendar.date(bySettingHour: hours[index], minute: 0, second: 0, of: day),
                      calendar.isDate(scheduled, inSameDayAs: day),
                      let id = UUID(uuidString: String(format: "A13D0000-0000-5000-8000-%012d", (offset + 13) * 6 + index + 1)) else { throw DemoAccountError.invalidAnchor }
                // Early-day rehearsals still show the full fictional baseline. Never
                // schedule today's later drinks in the future; the entries remain labelled simulated.
                let date = offset == 0 ? min(scheduled, anchor) : scheduled
                guard date <= anchor else { throw DemoAccountError.invalidAnchor }
                entries.append(Entry(id: id, request: CreateBeverageRequest(category: categories[index],
                    consumedMl: volumes[index], consumedAt: date, timezone: zone.identifier, source: "manual")))
            }
        }
        guard Set(entries.map { calendar.startOfDay(for: $0.request.consumedAt) }).count == 14 else { throw DemoAccountError.invalidAnchor }
        return Self(entries: entries, dailyGoalMl: 3000,
            profile: GoalProfile(ageYears: 30, referenceGroup: .men, eligibility: .generalAdult,
                heightCm: 178, weightKg: 75, supplements: [.creatine]))
    }
}

/// Resumable preparation only. A ready marker deliberately does not repair deleted
/// entries, change goals/profiles, or move the original fourteen-day window.
@MainActor final class DemoAccountSeeder {
    private enum State: String, Codable { case initializing, ready, resetting }
    private struct Marker: Codable {
        let version: String
        var state: State
        let anchorSeconds: Int64
        let timezone: String
        var anchor: Date { Date(timeIntervalSince1970: Double(anchorSeconds)) }
        func plan() throws -> DemoSeedPlan {
            guard version == "demo-account-v1", let zone = TimeZone(identifier: timezone) else { throw DemoAccountError.marker }
            return try DemoSeedPlan.make(now: anchor, zone: zone)
        }
    }
    private let service: LocalBeverageService
    private let profiles: GoalProfileStore
    private let markerURL: URL
    private let trustedRoot: URL
    private let inspectNode: ((URL) throws -> stat?)?
    // MainActor methods suspend at service calls. Prevent overlapping preparations
    // across seeder instances from observing a half-published state in this process.
    private static var activeMarkers: Set<String> = []
    private static let maximumBytes = 1024

    init(service: LocalBeverageService, profiles: GoalProfileStore, markerURL: URL,
         trustedRoot: URL = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).resolvingSymlinksInPath(),
         inspectNode: ((URL) throws -> stat?)? = nil) {
        self.service = service; self.profiles = profiles; self.markerURL = markerURL.standardizedFileURL
        self.trustedRoot = trustedRoot.standardizedFileURL; self.inspectNode = inspectNode
    }

    func prepare(bundleIdentifier: String?, now: Date, zone: TimeZone) async throws -> DemoSeedPlan {
        try guardBundle(bundleIdentifier)
        try enter(); defer { Self.activeMarkers.remove(markerURL.path) }
        if let saved = try readMarker() { return try await resume(saved, now: now) }
        let saved = try newMarker(state: .initializing, now: now, zone: zone)
        try await requireEmpty(now: now)
        try writeMarker(saved) // Publish the anchor before the first local mutation.
        return try await resume(saved, now: now)
    }

    func reset(bundleIdentifier: String?, now: Date, zone: TimeZone) async throws -> DemoSeedPlan {
        try guardBundle(bundleIdentifier)
        try enter(); defer { Self.activeMarkers.remove(markerURL.path) }
        // Even explicit reset cannot turn a corrupt/missing identity into permission
        // to erase unknown data. Only a validated demo marker or empty destination qualifies.
        if try readMarker() == nil { try await requireEmpty(now: now) }
        let saved = try newMarker(state: .resetting, now: now, zone: zone)
        try writeMarker(saved)
        return try await resume(saved, now: now)
    }

    private func guardBundle(_ identifier: String?) throws {
        guard DemoAccount.permits(bundleIdentifier: identifier) else { throw DemoAccountError.wrongBundle }
    }
    private func enter() throws {
        guard Self.activeMarkers.insert(markerURL.path).inserted else { throw DemoAccountError.busy }
    }
    private func newMarker(state: State, now: Date, zone: TimeZone) throws -> Marker {
        _ = try DemoSeedPlan.make(now: now, zone: zone)
        return Marker(version: "demo-account-v1", state: state,
            anchorSeconds: Int64(now.timeIntervalSince1970.rounded(.down)), timezone: zone.identifier)
    }
    private func requireEmpty(now: Date) async throws {
        let logs = try await service.listBeverages(), goal = try await service.goalSettings()
        guard profiles.canSave else { throw GoalProfileStoreError.unavailable }
        try profiles.reload(now: now)
        guard logs.isEmpty, goal.daily_beverage_goal_ml == nil, profiles.profile == nil else { throw DemoAccountError.existingData }
    }
    private func resume(_ saved: Marker, now: Date) async throws -> DemoSeedPlan {
        let plan = try saved.plan()
        if saved.state == .ready { return plan }
        // Do not shift a persisted anchor or submit even one future-dated request
        // after rollback. The exact requests can resume when the clock recovers.
        guard now.timeIntervalSince1970.isFinite, plan.entries.allSatisfy({ $0.request.consumedAt <= now }) else { throw DemoAccountError.clockRollback }
        guard profiles.canSave else { throw GoalProfileStoreError.unavailable }
        var initializing = saved
        if saved.state == .resetting {
            _ = try await service.deleteAllData()
            try profiles.deleteCurrent() // Never touches another connection's profile.
            initializing.state = .initializing
            try writeMarker(initializing)
        }
        let logs = try await service.listBeverages()
        guard Set(logs.map(\.id)).isSubset(of: Set(plan.entries.map(\.id))) else { throw DemoAccountError.existingData }
        for entry in plan.entries {
            _ = try await service.createBeverage(entry.request, idempotencyKey: entry.id)
        }
        _ = try await service.updateGoal(plan.dailyGoalMl)
        try profiles.save(plan.profile, consent: true, now: now)
        initializing.state = .ready
        try writeMarker(initializing)
        return plan
    }

    /// lstat catches dangling links. Inspect only the trusted container and its
    /// descendants; physical iOS may deny metadata access to filesystem ancestors.
    private func attributes(_ url: URL) throws -> stat? {
        if let inspectNode { return try inspectNode(url) }
        var node = stat()
        guard lstat(url.path, &node) == 0 else {
            if errno == ENOENT { return nil }
            throw DemoAccountError.marker
        }
        return node
    }
    private func checkPath() throws {
        let rootComponents = trustedRoot.pathComponents, markerComponents = markerURL.pathComponents
        // Check lexical containment before performing any filesystem operation.
        // Component comparison rejects prefix siblings, '..' escapes, and the root itself.
        guard trustedRoot.isFileURL, markerURL.isFileURL, trustedRoot.path.hasPrefix("/"),
              rootComponents.count > 1, markerComponents.count > rootComponents.count,
              Array(markerComponents.prefix(rootComponents.count)) == rootComponents else { throw DemoAccountError.marker }
        guard let root = try attributes(trustedRoot),
              root.st_mode & mode_t(S_IFMT) == mode_t(S_IFDIR) else { throw DemoAccountError.marker }
        var current = trustedRoot
        for component in markerComponents.dropFirst(rootComponents.count).dropLast() {
            current.appendPathComponent(component, isDirectory: true)
            if let node = try attributes(current) {
                guard node.st_mode & mode_t(S_IFMT) == mode_t(S_IFDIR) else { throw DemoAccountError.marker }
            }
        }
        if let node = try attributes(markerURL) {
            guard node.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), node.st_size <= Self.maximumBytes else { throw DemoAccountError.marker }
        }
    }
    private func readMarker() throws -> Marker? {
        try checkPath()
        guard try attributes(markerURL) != nil else { return nil }
        let descriptor = open(markerURL.path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw DemoAccountError.marker }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0, opened.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG),
              opened.st_size <= Self.maximumBytes else { throw DemoAccountError.marker }
        do {
            let data = try handle.read(upToCount: Self.maximumBytes + 1) ?? Data()
            guard data.count <= Self.maximumBytes,
                  let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  Set(object.keys) == ["version", "state", "anchorSeconds", "timezone"] else { throw DemoAccountError.marker }
            let marker = try JSONDecoder().decode(Marker.self, from: data)
            _ = try marker.plan()
            return marker
        } catch { throw DemoAccountError.marker }
    }
    private func writeMarker(_ marker: Marker) throws {
        try checkPath()
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let bytes = try encoder.encode(marker)
        guard bytes.count <= Self.maximumBytes else { throw DemoAccountError.marker }
        try OnDeviceProtectedFile.write(bytes, to: markerURL)
    }
}
