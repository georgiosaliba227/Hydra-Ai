import XCTest
@testable import HydraAI

final class DailyContextAppConfigurationTests: XCTestCase {
    func testBackgroundRefreshAndLocationDisclosureArePresentInBuiltApp() {
        let info = Bundle.main.infoDictionary ?? [:]
        XCTAssertTrue((info["BGTaskSchedulerPermittedIdentifiers"] as? [String] ?? [])
            .contains("com.georgiosaliba.hydraai.dailycontext"))
        XCTAssertTrue((info["UIBackgroundModes"] as? [String] ?? []).contains("fetch"))
        let disclosure = info["NSLocationWhenInUseUsageDescription"] as? String ?? ""
        XCTAssertTrue(disclosure.contains("rounded"))
        XCTAssertTrue(disclosure.contains("saved on this iPhone"))
    }
}
