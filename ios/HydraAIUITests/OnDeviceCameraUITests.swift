import XCTest

/// Generated label pixels, real bundled Meta inference, no backend or provider.
final class OnDeviceCameraUITests: XCTestCase {
    func testOfflineRealInferenceEditConfirmAndRestart() throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Simulator-only generated-image test; physical airplane-mode verification is separate")
        #endif
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchEnvironment=["HYDRA_TEST_ON_DEVICE":"1","HYDRA_TEST_PHOTO_FIXTURE":"1","HYDRA_TEST_ON_DEVICE_LABEL_FIXTURE":"1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout:15))
        app.tabBars.buttons["Settings"].tap()
        XCTAssertEqual(app.switches["onDeviceMode"].value as? String,"1")
        XCTAssertFalse(app.textFields["backendURL"].exists)
        app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total=app.descendants(matching:.any).matching(identifier:"dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout:15))
        let initial=try XCTUnwrap(Int(total.value as? String ?? ""))
        app.tabBars.buttons["Camera"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout:10))
        app.buttons["syntheticPhoto"].tap()
        XCTAssertFalse(app.buttons["mockScenario"].exists)
        XCTAssertFalse(app.switches["metaPhotoConsent"].exists)
        let consent=app.switches["photoConsent"]
        for _ in 0..<4 where !consent.isHittable { app.swipeUp() }
        consent.switches.firstMatch.tap()
        app.buttons["analyzePhoto"].tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout:60))
        XCTAssertEqual(app.staticTexts["photoVolume"].label,"500 mL")
        XCTAssertEqual(app.staticTexts["consumptionAssumptionSummary"].label,"Confirm logs the whole drink.")
        XCTAssertFalse(app.switches["shareCorrectionTraining"].exists)
        app.buttons["editRecognitionEntry"].tap()
        let name=app.textFields["photoIdentity"]
        XCTAssertTrue(name.waitForExistence(timeout:10))
        name.tap(withNumberOfTaps:3,numberOfTouches:1)
        let existing=name.value as? String ?? ""
        name.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:existing.count))
        name.typeText("Offline test water")
        if app.buttons["photoKeyboardDone"].exists { app.buttons["photoKeyboardDone"].tap() }
        app.buttons["photoDrinkType"].tap(); app.buttons["Water"].tap()
        let attachment=XCTAttachment(screenshot:app.screenshot()); attachment.name="Real on-device model review";attachment.lifetime = .keepAlways;add(attachment)
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout:15))
        app.tabBars.buttons["Today"].tap()
        let expected=String(initial+500)
        XCTAssertEqual(XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:NSPredicate(format:"value == %@",expected),object:total)],timeout:15),.completed)
        app.terminate(); app.launchEnvironment=[:]; app.launch()
        XCTAssertTrue(app.tabBars.buttons["Today"].waitForExistence(timeout:15))
        XCTAssertEqual(XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:NSPredicate(format:"value == %@",expected),object:total)],timeout:15),.completed)
        app.tabBars.buttons["History"].tap()
        XCTAssertTrue(app.descendants(matching:.any).matching(NSPredicate(format:"identifier == 'beverageRow' AND label CONTAINS 'Offline Test Water'")).firstMatch.waitForExistence(timeout:15))
    }
}
