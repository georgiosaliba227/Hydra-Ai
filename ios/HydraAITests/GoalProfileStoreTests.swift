import XCTest
@testable import HydraAI

final class GoalProfileStoreTests: XCTestCase {
    private let now = ISO8601DateFormatter().date(from: "2026-11-03T12:00:00Z")!
    private var configuration: APIConfiguration { .init(baseURL: "http://127.0.0.1:8000", token: String(repeating: "a", count: 32), offline: false) }
    private var answer: GoalProfile { .init(ageYears: 27, referenceGroup: .men, eligibility: .generalAdult, heightCm: 180, weightKg: 75, supplements: [.creatine]) }
    private func folder() -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    private func file(_ folder: URL, _ scope: UUID) -> URL { folder.appendingPathComponent(scope.uuidString + ".json") }
    @MainActor private func store(_ folder: URL, _ scope: UUID) -> GoalProfileStore {
        let store = GoalProfileStore(directory: folder, scopeResolver: { _ in scope })
        store.configure(configuration, now: now)
        return store
    }

    @MainActor func testExplicitConsentBeforeCreatingFilesAndConnectionRestoration() throws {
        let folder = folder(), first = UUID(), second = UUID()
        let store = GoalProfileStore(directory: folder, scopeResolver: { $0.token.first == "a" ? first : second })
        store.configure(configuration, now: now)
        XCTAssertTrue(store.canSave)
        XCTAssertNil(store.profile)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertThrowsError(try store.save(answer, consent: false, now: now))
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        try store.save(answer, consent: true, now: now)
        XCTAssertEqual(self.store(folder, first).profile, answer)
        var other = configuration; other.token = String(repeating: "b", count: 32)
        store.configure(other, now: now)
        XCTAssertNil(store.profile)
        var different = answer; different.ageYears = 45
        try store.save(different, consent: true, now: now)
        store.configure(configuration, now: now)
        XCTAssertEqual(store.profile, answer)
        XCTAssertEqual(self.store(folder, second).profile, different)
    }

    @MainActor func testOfflineInvalidAndUnavailableScopeNeverSaveOrResolveInvalidConnections() throws {
        let folder = folder()
        var resolutions = 0
        let store = GoalProfileStore(directory: folder, scopeResolver: { _ in resolutions += 1; throw URLError(.notConnectedToInternet) })
        var offline = configuration; offline.offline = true
        var invalid = configuration; invalid.token = "short"
        for config in [offline, invalid, configuration] {
            store.configure(config, now: now)
            XCTAssertFalse(store.canSave)
            XCTAssertThrowsError(try store.save(answer, consent: true, now: now))
            XCTAssertNil(store.profile)
        }
        XCTAssertEqual(resolutions, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
    }

    @MainActor func testInvalidSavePreservesOldProfileAndBytes() throws {
        let folder = folder(), scope = UUID(), store = store(folder, scope)
        try store.save(answer, consent: true, now: now)
        let old = try Data(contentsOf: file(folder, scope))
        var invalid = answer; invalid.heightCm = -1
        XCTAssertThrowsError(try store.save(invalid, consent: true, now: now))
        XCTAssertEqual(store.profile, answer)
        XCTAssertEqual(try Data(contentsOf: file(folder, scope)), old)
    }

    @MainActor func testMalformedOversizedWrongVersionWrongScopeAndUnknownFieldsPreserveEvidence() throws {
        for kind in ["broken", "oversize", "version", "scope", "extra", "profile-extra", "invalid-profile"] {
            let folder = folder(), scope = UUID(), store = store(folder, scope)
            try store.save(answer, consent: true, now: now)
            let file = file(folder, scope)
            var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
            switch kind {
            case "version": object["version"] = 2
            case "scope": object["scope"] = UUID().uuidString
            case "extra": object["token"] = "unrelated"
            case "profile-extra", "invalid-profile":
                var profile = try XCTUnwrap(object["profile"] as? [String: Any])
                profile[kind == "profile-extra" ? "unknown" : "heightCm"] = -1
                object["profile"] = profile
            default: break
            }
            let evidence = kind == "broken" ? Data("broken".utf8) : kind == "oversize" ? Data(repeating: 32, count: 16_385) : try JSONSerialization.data(withJSONObject: object)
            try evidence.write(to: file)
            XCTAssertThrowsError(try store.reload(now: now), kind)
            XCTAssertFalse(store.canSave, kind)
            XCTAssertNotNil(store.errorMessage, kind)
            XCTAssertEqual(store.profile, answer, kind)
            XCTAssertThrowsError(try store.save(answer, consent: true, now: now), kind)
            XCTAssertEqual(try Data(contentsOf: file), evidence, kind)
            try store.deleteCurrent()
            XCTAssertTrue(store.canSave)
            XCTAssertNil(store.profile)
            XCTAssertNil(store.errorMessage)
            try store.save(answer, consent: true, now: now)
        }
    }

    @MainActor func testFileSymlinksIncludingDanglingLinksNeverReadOrOverwriteTarget() throws {
        for dangling in [false, true] {
            let folder = folder(), scope = UUID(), target = self.folder()
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let evidence = Data("private outside evidence".utf8)
            if !dangling { try evidence.write(to: target) }
            let path = file(folder, scope)
            try FileManager.default.createSymbolicLink(at: path, withDestinationURL: target)
            let store = store(folder, scope)
            XCTAssertFalse(store.canSave)
            XCTAssertNil(store.profile)
            XCTAssertThrowsError(try store.save(answer, consent: true, now: now))
            XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: path.path), target.path)
            if !dangling { XCTAssertEqual(try Data(contentsOf: target), evidence) }
            else { XCTAssertFalse(FileManager.default.fileExists(atPath: target.path)) }
            try store.deleteCurrent()
            XCTAssertTrue(store.canSave)
            if !dangling { XCTAssertEqual(try Data(contentsOf: target), evidence) }
        }
    }

    @MainActor func testParentAndDirectorySymlinksIncludingDanglingLinksBlockSave() throws {
        for dangling in [false, true] {
            for nested in [false, true] {
                let link = folder(), target = folder(), scope = UUID()
                if !dangling { try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true) }
                try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
                let directory = nested ? link.appendingPathComponent("nested") : link
                let store = store(directory, scope)
                XCTAssertFalse(store.canSave)
                XCTAssertThrowsError(try store.save(answer, consent: true, now: now))
                XCTAssertFalse(FileManager.default.fileExists(atPath: target.appendingPathComponent("nested").path))
                XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: link.path), target.path)
            }
        }
    }

    @MainActor func testCorruptionAppearingAfterConfigurationBlocksOverwriteAndPreservesCachedProfile() throws {
        let folder = folder(), scope = UUID(), store = store(folder, scope)
        try store.save(answer, consent: true, now: now)
        let evidence = Data("changed after configure".utf8)
        try evidence.write(to: file(folder, scope))
        XCTAssertThrowsError(try store.save(answer, consent: true, now: now))
        XCTAssertFalse(store.canSave)
        XCTAssertEqual(store.profile, answer)
        XCTAssertEqual(try Data(contentsOf: file(folder, scope)), evidence)
    }

    @MainActor func testProfileOnlyExportAndSelectiveAndAllDeletion() throws {
        let folder = folder(), first = UUID(), second = UUID()
        let store = store(folder, first), other = self.store(folder, second)
        XCTAssertThrowsError(try store.exportData(now: now))
        try store.save(answer, consent: true, now: now)
        try other.save(answer, consent: true, now: now)
        let export = try store.exportData(now: now)
        XCTAssertEqual(try JSONDecoder().decode(GoalProfile.self, from: export), answer)
        let text = String(decoding: export, as: UTF8.self)
        for forbidden in [configuration.baseURL, configuration.token, first.uuidString, second.uuidString, "scope", "tokenFingerprint", "endpoint"] {
            XCTAssertFalse(text.contains(forbidden), forbidden)
        }
        try store.deleteCurrent()
        XCTAssertNil(self.store(folder, first).profile)
        XCTAssertEqual(self.store(folder, second).profile, answer)
        try store.deleteAll()
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertNil(self.store(folder, second).profile)
    }

    @MainActor func testWriteFailureKeepsPreviouslySavedProfileAndFile() throws {
        let folder = folder(), scope = UUID(), store = store(folder, scope)
        try store.save(answer, consent: true, now: now)
        let evidence = try Data(contentsOf: file(folder, scope))
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: folder.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: folder.path) }
        var next = answer; next.ageYears = 45
        XCTAssertThrowsError(try store.save(next, consent: true, now: now))
        XCTAssertEqual(store.profile, answer)
        XCTAssertEqual(try Data(contentsOf: file(folder, scope)), evidence)
        XCTAssertFalse(store.canSave)
        XCTAssertNotNil(store.errorMessage)
    }

    @MainActor func testDeleteAllUnlinksUnsafeDirectoryWithoutDeletingItsTarget() throws {
        let link = folder(), target = folder(), scope = UUID()
        try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
        let evidence = Data("outside evidence".utf8), outside = target.appendingPathComponent("keep.json")
        try evidence.write(to: outside)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
        let store = store(link, scope)
        XCTAssertFalse(store.canSave)
        try store.deleteAll()
        XCTAssertEqual(try Data(contentsOf: outside), evidence)
        XCTAssertThrowsError(try FileManager.default.destinationOfSymbolicLink(atPath: link.path))
    }

    @MainActor func testBackupExclusionAndProtectionOnDirectoryAndFile() throws {
        let folder = folder(), scope = UUID(), store = store(folder, scope)
        try store.save(answer, consent: true, now: now)
        for url in [folder, file(folder, scope)] {
            XCTAssertEqual(try url.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
            #if !targetEnvironment(simulator)
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            let protection = (attributes[.protectionKey] as? FileProtectionType)?.rawValue ?? (attributes[.protectionKey] as? String)
            XCTAssertEqual(protection, FileProtectionType.complete.rawValue)
            #endif
        }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: folder.path), [scope.uuidString + ".json"])
    }
}
