import XCTest
@testable import HydraAI

@MainActor
final class GoalLifecycleTests: XCTestCase {
    private let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)

    func testLateGoalReadCannotReturnAnotherConnectionsValue() async throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let service = SuspendedGoalService(), store = makeStore(service)
        let started = await service.readStarted
        let request = Task { try await store.currentGoal() }
        await fulfillment(of: [started], timeout: 2)
        try store.configure(.init(baseURL: configuration.baseURL, token: configuration.token, offline: true))
        await service.releaseRead()
        do { _ = try await request.value; XCTFail("A connection change must reject the old goal read") }
        catch { }
        XCTAssertNil(store.summary)
    }

    func testLateGoalSaveCannotRefreshOrReportSuccessForNewConnection() async throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let service = SuspendedGoalService(), store = makeStore(service)
        let started = await service.saveStarted
        let request = Task { try await store.setGoal(3000) }
        await fulfillment(of: [started], timeout: 2)
        try store.configure(.init(baseURL: configuration.baseURL, token: configuration.token, offline: true))
        await service.releaseSaves()
        do { try await request.value; XCTFail("Old confirmation must not succeed in the new connection") }
        catch { }
        XCTAssertNil(store.summary)
    }

    func testGoalConfirmationsAreSerialized() async throws {
        let service = SuspendedGoalService(), store = makeStore(service)
        let started = await service.saveStarted, secondStarted = await service.secondSaveStarted
        secondStarted.isInverted = true
        let first = Task { do { try await store.setGoal(3000); return true } catch { return false } }
        await fulfillment(of: [started], timeout: 2)
        let second = Task { do { try await store.setGoal(2200); return true } catch { return false } }
        await fulfillment(of: [secondStarted], timeout: 0.15)
        let calls = await service.saveCalls
        XCTAssertEqual(calls, 1)
        await service.releaseSaves()
        let firstSucceeded = await first.value, secondSucceeded = await second.value
        XCTAssertTrue(firstSucceeded)
        XCTAssertFalse(secondSucceeded)
    }

    func testGoalConfirmationBlocksDeletionUntilItsOutcomeIsKnown() async throws {
        let service = SuspendedGoalService(), store = makeStore(service)
        let started = await service.saveStarted
        let request = Task { try await store.setGoal(3000) }
        await fulfillment(of: [started], timeout: 2)
        do { _ = try await store.deleteAllData(); XCTFail("Deletion must not race a goal write") } catch { }
        let deletes = await service.deleteCalls
        XCTAssertEqual(deletes, 0)
        await service.releaseSaves(); try await request.value
    }

    func testReconfiguringCannotReleaseAnOutstandingGoalWrite() async throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let service = SuspendedGoalService(), store = makeStore(service)
        let started = await service.saveStarted
        let first = Task { do { try await store.setGoal(3000) } catch { } }
        await fulfillment(of: [started], timeout: 2)
        try store.configure(configuration)
        XCTAssertTrue(store.isSettingGoal, "The old PUT is still in flight")
        do { try await store.setGoal(2200); XCTFail("A second write must remain blocked") }
        catch GoalMutationError.busy { }
        catch { XCTFail("Expected the mutation gate before contacting the replacement service") }
        await service.releaseSaves(); await first.value
        XCTAssertFalse(store.isSettingGoal)
    }

    func testDeletionBlocksGoalConfirmationUntilItFinishes() async throws {
        let service = SuspendedGoalService(suspendDeletion: true), store = makeStore(service)
        let started = await service.deleteStarted, saveStarted = await service.saveStarted
        saveStarted.isInverted = true
        let deletion = Task { try await store.deleteAllData() }
        await fulfillment(of: [started], timeout: 2)
        let goal = Task { do { try await store.setGoal(3000); return true } catch { return false } }
        await fulfillment(of: [saveStarted], timeout: 0.15)
        let calls = await service.saveCalls
        XCTAssertEqual(calls, 0)
        await service.releaseSaves(); await service.releaseDeletion()
        _ = try await deletion.value
        let goalSucceeded = await goal.value
        XCTAssertFalse(goalSucceeded)
    }

    private func makeStore(_ service: SuspendedGoalService) -> BeverageStore {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return BeverageStore(service: service, pendingURL: directory.appendingPathComponent("pending.json"),
            configuration: configuration, calibrationHistory: CalibrationHistoryStore(directory: directory.appendingPathComponent("history")),
            goalProfiles: GoalProfileStore(directory: directory.appendingPathComponent("profiles")))
    }
}

private actor SuspendedGoalService: BeverageService {
    let readStarted = XCTestExpectation(description: "Goal read suspended")
    let saveStarted = XCTestExpectation(description: "Goal confirmation suspended")
    let secondSaveStarted = XCTestExpectation(description: "A second goal mutation must not start")
    let deleteStarted = XCTestExpectation(description: "Delete suspended")
    private let suspendDeletion: Bool
    private var deleteContinuation: CheckedContinuation<Int, Never>?
    private(set) var saveCalls = 0
    private(set) var deleteCalls = 0
    private var readContinuation: CheckedContinuation<GoalSettings, Error>?
    private var saveContinuations: [(Int?, CheckedContinuation<GoalSettings, Error>)] = []

    init(suspendDeletion: Bool = false) { self.suspendDeletion = suspendDeletion }

    func goalSettings() async throws -> GoalSettings {
        try await withCheckedThrowingContinuation { continuation in
            readContinuation = continuation; readStarted.fulfill()
        }
    }
    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings {
        saveCalls += 1
        return try await withCheckedThrowingContinuation { continuation in
            saveContinuations.append((milliliters, continuation))
            if saveCalls == 1 { saveStarted.fulfill() } else { secondSaveStarted.fulfill() }
        }
    }
    func releaseRead() {
        readContinuation?.resume(returning: settings(3000)); readContinuation = nil
    }
    func releaseSaves() {
        let copies = saveContinuations; saveContinuations = []
        for (value, continuation) in copies { continuation.resume(returning: settings(value)) }
    }
    func deleteAllData() async throws -> Int {
        deleteCalls += 1
        if suspendDeletion {
            return await withCheckedContinuation { deleteContinuation = $0; deleteStarted.fulfill() }
        }
        return 0
    }
    func releaseDeletion() { deleteContinuation?.resume(returning: 0); deleteContinuation = nil }
    private func settings(_ value: Int?) -> GoalSettings {
        .init(version: "settings-v1", daily_beverage_goal_ml: value, goal_basis: "user_confirmed")
    }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        .init(localDate: date, timezone: timezone, beverageTotalMl: 0, estimatedWaterMl: nil, forecastStatus: "insufficient_data")
    }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        throw ServiceError.invalidResponse
    }
}
