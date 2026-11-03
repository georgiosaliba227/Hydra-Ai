import XCTest

/// Explicitly opted-in saved-result GETs only; no Meta dispatch or personal records.
final class OwnerSyntheticWonderUITests: XCTestCase {
    func testSavedSyntheticWonderReplayShowsEightSectionsAndUnverifiedFinality() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_OWNER_WONDER_REPLAY"] == "1",
              let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires an explicitly enabled synthetic saved-result backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launchHydra()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        app.buttons["saveConnection"].tap()
        let open = app.buttons["openOwnerWonderResult"]
        reveal(open, in: app); open.tap()
        XCTAssertTrue(app.staticTexts["ownerWonderSyntheticLabel"].waitForExistence(timeout: 5))
        let load = app.buttons["loadOwnerWonderResult"]
        load.tap()
        XCTAssertTrue(app.staticTexts["ownerWonderResult"].waitForExistence(timeout: 15))
        for id in ["summary", "workout_loss", "activity", "environment", "beverages", "trends", "uncertainty", "measurement"] {
            let section = app.buttons["ownerWonderSection-\(id)"]
            reveal(section, in: app)
            XCTAssertTrue(section.exists, "Missing section \(id)")
            section.tap()
            let evidence = app.staticTexts["ownerWonderEvidence-\(id)"]
            reveal(evidence, in: app)
            XCTAssertEqual(evidence.label, "Simulated evidence")
            for _ in 0..<10 where !section.isHittable { app.swipeDown() }
            XCTAssertTrue(section.isHittable)
            section.tap()
        }
        let finality = app.staticTexts["ownerWonderFinality"]
        reveal(finality, in: app)
        XCTAssertEqual(finality.label, "Final invoice unverified. Provider extras are unverified.")
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Saved synthetic Wonder request record"
        screenshot.lifetime = .keepAlways; add(screenshot)
        // Another explicit load is a free GET. The operator independently checks ledger preservation.
        for _ in 0..<10 where !load.isHittable { app.swipeDown() }
        XCTAssertTrue(load.isHittable); load.tap()
        XCTAssertTrue(app.staticTexts["ownerWonderResult"].waitForExistence(timeout: 15))
    }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<10 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable, "Expected saved-result control to be reachable")
    }
}
