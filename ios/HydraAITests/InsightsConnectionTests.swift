import XCTest
@testable import HydraAI

final class InsightsConnectionTests: XCTestCase {
    private let url = "http://127.0.0.1:8772"
    private let token = String(repeating: "s", count: 32)

    func testFirstInstallStartsOnDeviceWithoutEnablingBackendFeatures() throws {
        let suite = "HydraUITests.Configuration.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = APIConfiguration.load(defaults: defaults)
        XCTAssertTrue(first.onDevice)
        XCTAssertFalse(first.offline)
        XCTAssertFalse(first.insightsEnabled)
        XCTAssertNil(first.backendInsightsConfiguration)
        defaults.set("http://127.0.0.1:8771", forKey: "hydra.backendURL")
        XCTAssertFalse(APIConfiguration.load(defaults: defaults).onDevice, "An existing server destination must be preserved")
        defaults.set(true, forKey: "hydra.offline")
        XCTAssertTrue(APIConfiguration.load(defaults: defaults).offline)
    }

    func testServerModeUsesItsExistingConnection() throws {
        let server = APIConfiguration(baseURL: url, token: token, offline: false)
        let insights = try XCTUnwrap(server.backendInsightsConfiguration)
        XCTAssertEqual(insights.baseURL, url)
        XCTAssertFalse(insights.onDevice)
    }

    func testOnDeviceRequiresSeparateOptInAndPreservesLocalDestination() throws {
        var local = APIConfiguration(baseURL: url, token: token, offline: false, onDevice: true)
        XCTAssertNil(local.backendInsightsConfiguration)
        local.insightsEnabled = true
        let insights = try XCTUnwrap(local.backendInsightsConfiguration)
        XCTAssertFalse(insights.onDevice)
        XCTAssertFalse(insights.offline)
        XCTAssertTrue(local.onDevice)
        XCTAssertEqual(insights.token, token)
    }

    func testDemoAndInvalidConnectionsHaveNoInsightsRoute() {
        XCTAssertNil(APIConfiguration(baseURL: url, token: token, offline: true, insightsEnabled: true).backendInsightsConfiguration)
        XCTAssertNil(APIConfiguration(baseURL: "http://example.com", token: token, offline: false, onDevice: true, insightsEnabled: true).backendInsightsConfiguration)
        XCTAssertNil(APIConfiguration(baseURL: url, token: "short", offline: false, onDevice: true, insightsEnabled: true).backendInsightsConfiguration)
    }

    func testOptionalConnectionPersistsWithoutChangingOnDeviceMode() throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let old = UserDefaults.standard.object(forKey: "hydra.backendInsights")
        defer { UserDefaults.standard.set(old, forKey: "hydra.backendInsights") }
        try APIConfiguration(baseURL: url, token: token, offline: false, onDevice: true, insightsEnabled: true).save()
        let reloaded = APIConfiguration.load()
        XCTAssertTrue(reloaded.onDevice)
        XCTAssertTrue(reloaded.insightsEnabled)
        XCTAssertNotNil(reloaded.backendInsightsConfiguration)
    }

    func testOptedInInvalidConnectionFailsBeforeChangingSavedDestination() throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let original = APIConfiguration(baseURL: url, token: token, offline: false, onDevice: true)
        try original.save()
        XCTAssertThrowsError(try APIConfiguration(baseURL: "http://example.com", token: "short", offline: false, onDevice: true, insightsEnabled: true).save())
        XCTAssertEqual(APIConfiguration.load().baseURL, url)
    }
}
