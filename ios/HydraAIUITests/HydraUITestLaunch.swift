import XCTest

extension XCUIApplication {
    /// Form rows can report hittable under the persistent tab bar. Bring the
    /// element's center into the actual content area before tapping.
    func revealFormElement(_ element: XCUIElement) {
        for _ in 0..<18 {
            if element.exists && element.isHittable {
                let top = navigationBars.firstMatch.frame.maxY
                let bottom = tabBars.firstMatch.frame.minY
                if element.frame.midY > top + 12 && element.frame.midY < bottom - 12 { return }
                if element.frame.midY <= top + 12 { swipeDown(); continue }
            }
            swipeUp()
        }
        XCTAssertTrue(element.isHittable)
    }

    /// Earlier workflows explicitly retain their metric fixtures and bypass the
    /// unrelated first-use sheet. New setup/unit tests use launch() directly.
    func launchHydra() {
        launchEnvironment["HYDRA_TEST_UNIT_SYSTEM"] = "metric"
        launchEnvironment["HYDRA_TEST_CONTEXT_SETUP"] = "skip"
        if launchEnvironment["HYDRA_TEST_CONTEXT_SUITE"] == nil {
            launchEnvironment["HYDRA_TEST_CONTEXT_SUITE"] = "HydraUITests.Legacy.\(UUID().uuidString)"
        }
        launch()
    }
}

extension XCUIElement {
    var metricMillilitersValue: Int? {
        guard let text = value as? String, text.hasSuffix(" mL") else { return nil }
        return Int(text.dropLast(3))
    }
}
