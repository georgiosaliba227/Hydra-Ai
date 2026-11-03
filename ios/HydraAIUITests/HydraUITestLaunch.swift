import XCTest

extension XCUIApplication {
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
