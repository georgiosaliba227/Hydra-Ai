import XCTest
@testable import HydraAI

final class DemoAccountTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_793_793_600) // Synthetic clock only.
    private let zone = TimeZone(identifier: "America/New_York")!
    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("demo-tests-\(UUID())")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    @MainActor private func profiles(_ root: URL) -> GoalProfileStore {
        let store = GoalProfileStore(directory: root.appendingPathComponent("profiles"))
        store.configure(APIConfiguration(baseURL: "", token: "", offline: false, onDevice: true), now: now)
        return store
    }
    private func requests(_ plan: DemoSeedPlan) throws -> Data {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]; encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(plan.entries.map(\.request))
    }
    private func marker(_ root: URL, state: String, anchor: Date, zone: TimeZone) throws {
        let bytes = try JSONSerialization.data(withJSONObject: ["version": "demo-account-v1", "state": state,
            "anchorSeconds": Int(anchor.timeIntervalSince1970.rounded(.down)), "timezone": zone.identifier])
        try bytes.write(to: root.appendingPathComponent("marker.json"))
    }

    func testIdentityRequiresTheExactDemoBundle() {
        XCTAssertEqual(DemoAccount.bundleIdentifier, "com.georgiosaliba.hydraai.demo")
        XCTAssertTrue(DemoAccount.permits(bundleIdentifier: DemoAccount.bundleIdentifier))
        for id in [nil, "com.georgiosaliba.hydraai", "com.georgiosaliba.hydraai.demo.other", "COM.georgiosaliba.hydraai.demo"] {
            XCTAssertFalse(DemoAccount.permits(bundleIdentifier: id))
        }
        XCTAssertEqual(DemoAccount.isActive, Bundle.main.bundleIdentifier == DemoAccount.bundleIdentifier)
    }

    func testPlanHasFourteenLocalDaysStableRequestsAnd2250TodayEvenAtMidnight() throws {
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone
        for clock in [now, calendar.startOfDay(for: now), now.addingTimeInterval(0.987)] {
            let plan = try DemoSeedPlan.make(now: clock, zone: zone)
            let repeated = try DemoSeedPlan.make(now: clock, zone: zone)
            XCTAssertEqual(plan.entries.map(\.id), repeated.entries.map(\.id))
            XCTAssertEqual(try requests(plan), try requests(repeated))
            XCTAssertEqual(Set(plan.entries.map(\.id)).count, plan.entries.count)
            XCTAssertEqual(Set(plan.entries.map { calendar.startOfDay(for: $0.request.consumedAt) }).count, 14)
            XCTAssertEqual(plan.entries.filter { calendar.isDate($0.request.consumedAt, inSameDayAs: clock) }.reduce(0) { $0 + $1.request.consumedMl }, 2250)
            XCTAssertEqual(plan.dailyGoalMl, 3000)
            XCTAssertTrue(plan.entries.allSatisfy { $0.request.consumedAt <= clock && $0.request.source == "manual" && $0.request.beverageType == nil })
            XCTAssertTrue(Set(plan.entries.map { $0.request.category }).isSubset(of: ["water", "coffee", "tea", "milk", "juice"]))
            try GoalProfileValidation.validate(plan.profile, now: clock)
            for entry in plan.entries { try entry.request.validate(now: clock, allowOnDevice: true) }
        }
    }

    @MainActor func testProductionPrepareAndResetLeaveAllFilesUnchanged() async throws {
        let root = try folder(), service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json"))
        let profiles = profiles(root), seeder = DemoAccountSeeder(service: service, profiles: profiles, markerURL: root.appendingPathComponent("marker.json"))
        for reset in [false, true] {
            do {
                if reset { _ = try await seeder.reset(bundleIdentifier: "com.georgiosaliba.hydraai", now: now, zone: zone) }
                else { _ = try await seeder.prepare(bundleIdentifier: nil, now: now, zone: zone) }
                XCTFail("Production bundle accepted")
            } catch { }
        }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [])
    }

    @MainActor func testReadyRelaunchPreservesDeletedEditedNewEntriesGoalAndProfile() async throws {
        let root = try folder(), service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json")), profiles = profiles(root)
        let url = root.appendingPathComponent("marker.json"), seeder = DemoAccountSeeder(service: service, profiles: profiles, markerURL: url)
        let plan = try await seeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone)
        let logs = try await service.listBeverages(), first = try XCTUnwrap(logs.first), second = logs[1]
        try await service.deleteBeverage(id: first.id, revision: first.revision)
        _ = try await service.updateBeverage(id: second.id, UpdateBeverageRequest(correcting: second, category: "juice", consumedMl: 123, consumedAt: second.consumedAt))
        _ = try await service.createBeverage(CreateBeverageRequest(category: "water", consumedMl: 250, consumedAt: now, timezone: zone.identifier, source: "manual"), idempotencyKey: UUID())
        _ = try await service.updateGoal(2800)
        var changed = plan.profile; changed.ageYears = 45
        try profiles.save(changed, consent: true, now: now)
        let before = try await service.exportData(), markerBefore = try Data(contentsOf: url)
        let relaunched = DemoAccountSeeder(service: service, profiles: profiles, markerURL: url)
        let restored = try await relaunched.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now.addingTimeInterval(86400), zone: TimeZone(identifier: "Asia/Tokyo")!)
        XCTAssertEqual(try requests(restored), try requests(plan))
        let after = try await service.exportData()
        XCTAssertEqual(after, before); XCTAssertEqual(profiles.profile, changed)
        XCTAssertEqual(try Data(contentsOf: url), markerBefore)
        XCTAssertEqual(try url.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        XCTAssertEqual((try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber)?.intValue, 0o600)
    }

    @MainActor func testInterruptedInitializationResumesWithTheOriginalNormalizedAnchor() async throws {
        let root = try folder(), clock = now.addingTimeInterval(0.987), plan = try DemoSeedPlan.make(now: clock, zone: zone)
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json")), profiles = profiles(root)
        try marker(root, state: "initializing", anchor: clock, zone: zone)
        for entry in plan.entries.prefix(7) { _ = try await service.createBeverage(entry.request, idempotencyKey: entry.id) }
        let restored = try await DemoAccountSeeder(service: service, profiles: profiles, markerURL: root.appendingPathComponent("marker.json")).prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now.addingTimeInterval(3600), zone: .gmt)
        let logs = try await service.listBeverages(), goal = try await service.goalSettings()
        XCTAssertEqual(Set(logs.map(\.id)), Set(plan.entries.map(\.id)))
        XCTAssertEqual(try requests(restored), try requests(plan))
        XCTAssertEqual(goal.daily_beverage_goal_ml, 3000); XCTAssertEqual(profiles.profile, plan.profile)
    }

    @MainActor func testResetAndInterruptedResetOnlyClearSuppliedLocalServices() async throws {
        let root = try folder(), otherRoot = try folder()
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json")), profiles = profiles(root)
        let other = LocalBeverageService(fileURL: otherRoot.appendingPathComponent("local.json")), otherProfiles = self.profiles(otherRoot)
        let otherSeeder = DemoAccountSeeder(service: other, profiles: otherProfiles, markerURL: otherRoot.appendingPathComponent("marker.json"))
        _ = try await otherSeeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone)
        let otherBefore = try await other.exportData(), otherProfile = otherProfiles.profile
        let seeder = DemoAccountSeeder(service: service, profiles: profiles, markerURL: root.appendingPathComponent("marker.json"))
        _ = try await seeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone)
        _ = try await service.updateGoal(2000)
        let reset = try await seeder.reset(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone)
        let resetLogs = try await service.listBeverages()
        XCTAssertEqual(resetLogs.count, reset.entries.count)
        try marker(root, state: "resetting", anchor: now, zone: zone)
        _ = try await service.deleteAllData() // Crash between the two reset deletions.
        _ = try await seeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone)
        let goal = try await service.goalSettings(), logs = try await service.listBeverages(), otherAfter = try await other.exportData()
        XCTAssertEqual(goal.daily_beverage_goal_ml, 3000); XCTAssertEqual(logs.count, reset.entries.count)
        XCTAssertEqual(otherBefore, otherAfter); XCTAssertEqual(otherProfile, otherProfiles.profile)
    }

    @MainActor func testMissingMarkerWithPreexistingRecordsGoalOrProfileFailsClosed() async throws {
        for kind in ["records", "goal", "profile"] {
            let root = try folder(), service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json")), profiles = profiles(root)
            if kind == "records" { _ = try await service.createBeverage(CreateBeverageRequest(category: "water", consumedMl: 100, consumedAt: now, timezone: zone.identifier, source: "manual"), idempotencyKey: UUID()) }
            if kind == "goal" { _ = try await service.updateGoal(2000) }
            if kind == "profile" { try profiles.save(GoalProfile(ageYears: 45), consent: true, now: now) }
            let before = try await service.exportData(), oldProfile = profiles.profile
            let seeder = DemoAccountSeeder(service: service, profiles: profiles, markerURL: root.appendingPathComponent("marker.json"))
            do { _ = try await seeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone); XCTFail("Unknown data merged: \(kind)") } catch { }
            let after = try await service.exportData()
            XCTAssertEqual(before, after); XCTAssertEqual(oldProfile, profiles.profile)
            XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("marker.json").path))
        }
    }

    @MainActor func testCorruptAndSymlinkMarkerFailBeforeMutationIncludingReset() async throws {
        for kind in ["corrupt", "symlink", "dangling", "ancestor"] {
            let root = try folder(), service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json")), profiles = profiles(root)
            let target = root.appendingPathComponent("target"); try Data("evidence".utf8).write(to: target)
            var url = root.appendingPathComponent("marker.json")
            if kind == "corrupt" { try Data("broken".utf8).write(to: url) }
            else if kind == "ancestor" {
                try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("linked"), withDestinationURL: root)
                url = root.appendingPathComponent("linked/marker.json")
            } else { try FileManager.default.createSymbolicLink(at: url, withDestinationURL: kind == "symlink" ? target : root.appendingPathComponent("missing")) }
            let seeder = DemoAccountSeeder(service: service, profiles: profiles, markerURL: url)
            do { _ = try await seeder.prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone); XCTFail(kind) } catch { }
            do { _ = try await seeder.reset(bundleIdentifier: DemoAccount.bundleIdentifier, now: now, zone: zone); XCTFail(kind) } catch { }
            XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("local.json").path))
            XCTAssertNil(profiles.profile); XCTAssertEqual(try String(contentsOf: target, encoding: .utf8), "evidence")
        }
    }

    @MainActor func testClockRollbackDefersIncompleteSeedWithoutChangingStableRequests() async throws {
        let root = try folder(), earlier = now.addingTimeInterval(-86400), plan = try DemoSeedPlan.make(now: now, zone: zone)
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("local.json"), now: { earlier }), profiles = profiles(root)
        try marker(root, state: "initializing", anchor: now, zone: zone)
        let markerBefore = try Data(contentsOf: root.appendingPathComponent("marker.json"))
        do { _ = try await DemoAccountSeeder(service: service, profiles: profiles, markerURL: root.appendingPathComponent("marker.json")).prepare(bundleIdentifier: DemoAccount.bundleIdentifier, now: earlier, zone: zone); XCTFail("Future records admitted") } catch { }
        let logs = try await service.listBeverages()
        XCTAssertTrue(logs.isEmpty); XCTAssertNil(profiles.profile)
        XCTAssertEqual(try Data(contentsOf: root.appendingPathComponent("marker.json")), markerBefore)
        XCTAssertTrue(plan.entries.contains { $0.request.consumedAt > earlier })
    }
}
