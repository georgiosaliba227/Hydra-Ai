import XCTest

/// Development verification on disposable simulator stores; final video is physical-phone footage.
final class DemoAccountUITests: XCTestCase {
    func testDemoIsLabelledAndResetDoesNotChangeNormalAccount() throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Synthetic demo regression is restricted to simulator verification")
        #endif
        guard ProcessInfo.processInfo.environment["HYDRA_E2E_DEMO_BUNDLE"] == "com.georgiosaliba.hydraai.demo" else {
            throw XCTSkip("Requires separately installed Hydra Demo build")
        }
        continueAfterFailure = false
        let normal = XCUIApplication()
        normal.launchEnvironment = ["HYDRA_TEST_ON_DEVICE": "1", "HYDRA_TEST_SKIP_GOAL_SETUP": "1"]
        normal.launch()
        let normalTotal = normal.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(normalTotal.waitForExistence(timeout: 15))
        let initialNormal = normalTotal.value as? String
        XCTAssertFalse(normal.staticTexts["demoAccountBadge"].exists)
        normal.terminate()

        let demo = XCUIApplication(bundleIdentifier: "com.georgiosaliba.hydraai.demo")
        let suite = "HydraUITests.Demo.\(UUID().uuidString)"
        demo.launchEnvironment = ["HYDRA_TEST_ON_DEVICE": "1", "HYDRA_TEST_SKIP_GOAL_SETUP": "1",
                                  "HYDRA_TEST_GOAL_PROFILE_SUITE": suite]
        demo.launch()
        XCTAssertTrue(demo.staticTexts["demoAccountBadge"].waitForExistence(timeout: 20))
        let total = demo.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '2250'"), object: total)], timeout: 15), .completed)
        demo.buttons["quickAdd-water-250"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '2500'"), object: total)], timeout: 10), .completed)
        demo.terminate(); demo.launch()
        XCTAssertTrue(total.waitForExistence(timeout: 20))
        XCTAssertEqual(total.value as? String, "2500", "Relaunch must preserve demo edits")
        demo.tabBars.buttons["Settings"].tap()
        let reset = demo.buttons["resetDemoAccount"]
        for _ in 0..<6 where !reset.isHittable { demo.swipeUp() }
        XCTAssertTrue(reset.waitForExistence(timeout: 10)); reset.tap()
        let confirm = demo.buttons.matching(identifier: "confirmResetDemoAccount").matching(NSPredicate(format: "label == %@", "Reset simulated account")).firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5)); confirm.tap()
        demo.tabBars.buttons["Today"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '2250'"), object: total)], timeout: 15), .completed)
        demo.terminate()

        normal.launch()
        XCTAssertTrue(normalTotal.waitForExistence(timeout: 15))
        XCTAssertEqual(normalTotal.value as? String, initialNormal, "The demo's bootstrap and reset must never mutate the normal app")
        normal.terminate()
    }
}
