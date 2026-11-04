import XCTest
import UIKit

/// Synthetic local progress and label pixels, real bundled inference, no backend/provider.
final class OnDeviceCameraUITests: XCTestCase {
    func testOnDeviceAnalyzeDoesNotRequireExtraPhotoToggle() throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Simulator-only generated-photo test")
        #endif
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchEnvironment=["HYDRA_TEST_ON_DEVICE":"1","HYDRA_TEST_PHOTO_FIXTURE":"1","HYDRA_TEST_ON_DEVICE_LABEL_FIXTURE":"1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Camera"].waitForExistence(timeout:15));app.tabBars.buttons["Camera"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout:10));app.buttons["syntheticPhoto"].tap()
        XCTAssertFalse(app.switches["photoConsent"].exists,"Tapping Analyze is the explicit request for local processing")
        let analyze=app.buttons["analyzePhoto"]
        for _ in 0..<4 where !analyze.isHittable {app.swipeUp()}
        XCTAssertEqual(analyze.label,"Analyze")
        XCTAssertTrue(analyze.isEnabled)
        XCTAssertFalse(app.staticTexts["photoVolume"].exists,"Selecting a photo must not run analysis automatically")
        analyze.tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout:60))
        XCTAssertEqual(app.staticTexts["photoVolume"].label,"500 mL")
        app.buttons["Cancel"].tap()
    }

    func testGoalWaterFillsInsideAtHalfAndFullGoal() throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Simulator-only synthetic progress check")
        #endif
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchEnvironment=["HYDRA_TEST_ON_DEVICE":"1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Today"].waitForExistence(timeout:15))
        let total=app.descendants(matching:.any).matching(identifier:"dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout:15))
        var initial=try XCTUnwrap(Int(total.value as? String ?? ""))
        if initial==0 {
            app.buttons["quickAdd-water-500"].tap()
            XCTAssertEqual(XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:NSPredicate(format:"value == '500'"),object:total)],timeout:15),.completed)
            initial=500
        }
        XCTAssertTrue((100...5_000).contains(initial),"Run on a fresh disposable simulator so both goal states can be tested")
        func setGoal(_ value:Int) {
            app.tabBars.buttons["Settings"].tap()
            let field=app.textFields["goalField"]
            XCTAssertTrue(field.waitForExistence(timeout:10))
            app.buttons["Clear goal"].tap()
            replace(field,with:String(value),app:app)
            XCTAssertEqual(field.value as? String,String(value))
            if app.buttons["Done"].exists { app.buttons["Done"].tap() }
            XCTAssertTrue(app.buttons["saveGoal"].isEnabled)
            app.buttons["saveGoal"].tap()
            let message=app.descendants(matching:.any).matching(identifier:"goalMessage").firstMatch
            XCTAssertEqual(XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == 'Goal saved.'"),object:message)],timeout:10),.completed)
            app.tabBars.buttons["Today"].tap()
        }
        func blueMinusRed(at point:CGPoint, image:CGImage) throws -> Int {
            let scale=CGFloat(image.width)/app.frame.width
            let crop=try XCTUnwrap(image.cropping(to:CGRect(x:point.x*scale-1,y:point.y*scale-1,width:3,height:3)))
            var pixel=[UInt8](repeating:0,count:4)
            try pixel.withUnsafeMutableBytes { bytes in
                let context=try XCTUnwrap(CGContext(data:bytes.baseAddress,width:1,height:1,bitsPerComponent:8,bytesPerRow:4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue))
                context.draw(crop,in:CGRect(x:0,y:0,width:1,height:1))
            }
            return Int(pixel[2])-Int(pixel[0])
        }
        func verifyArc(full:Bool) throws {
            let frame=total.frame
            // Wait for the water animation's rendered pixels, not just its text.
            let settled=XCTNSPredicateExpectation(predicate:NSPredicate { _,_ in
                guard let image=app.screenshot().image.cgImage,
                      let bottom=try? blueMinusRed(at:CGPoint(x:frame.midX-frame.width*0.28,y:frame.midY+frame.height*0.25),image:image),
                      let top=try? blueMinusRed(at:CGPoint(x:frame.midX-frame.width*0.28,y:frame.midY-frame.height*0.25),image:image) else { return false }
                return bottom>20 && (full ? top>20 : top<15)
            },object:nil)
            XCTAssertEqual(XCTWaiter.wait(for:[settled],timeout:5),.completed)
            let screenshot=app.screenshot()
            let image=try XCTUnwrap(screenshot.image.cgImage)
            let right=try blueMinusRed(at:CGPoint(x:frame.midX+frame.width*0.48,y:frame.midY),image:image)
            let left=try blueMinusRed(at:CGPoint(x:frame.midX-frame.width*0.48,y:frame.midY),image:image)
            let bottom=try blueMinusRed(at:CGPoint(x:frame.midX-frame.width*0.28,y:frame.midY+frame.height*0.25),image:image)
            let top=try blueMinusRed(at:CGPoint(x:frame.midX-frame.width*0.28,y:frame.midY-frame.height*0.25),image:image)
            let proof=XCTAttachment(screenshot:screenshot);proof.name=full ? "Full goal ring" : "Half goal ring";proof.lifetime = .keepAlways;add(proof)
            XCTAssertGreaterThan(right,90,"The right arc must visibly show progress")
            if full { XCTAssertGreaterThan(left,90,"The completed ring must fill on both sides") }
            else { XCTAssertLessThan(left,70,"Half progress must leave the left arc as the track") }
            XCTAssertGreaterThan(bottom,20,"Water must fill the lower interior of the circle")
            if full { XCTAssertGreaterThan(top,20,"Water must reach the upper interior at a full goal") }
            else { XCTAssertLessThan(top,15,"At half a goal, water must stay below the middle") }
        }
        setGoal(initial*2)
        let progress=app.descendants(matching:.any).matching(identifier:"goalProgress").firstMatch
        XCTAssertTrue(progress.waitForExistence(timeout:10))
        XCTAssertTrue(progress.label.contains("50%"))
        try verifyArc(full:false)
        setGoal(initial)
        XCTAssertTrue(progress.label.contains("Goal reached"))
        try verifyArc(full:true)
    }

    private func replace(_ field: XCUIElement, with text: String, app: XCUIApplication) {
        for _ in 0..<5 where !field.isHittable { app.swipeUp() }
        let value=field.value as? String ?? ""
        if value.isEmpty || value==field.placeholderValue {
            field.tap()
        } else {
            field.tap(withNumberOfTaps:3,numberOfTouches:1)
            field.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:value.count))
        }
        field.typeText(text)
        if app.buttons["photoKeyboardDone"].exists { app.buttons["photoKeyboardDone"].tap() }
    }

    func testContainerSizeCanBeCorrectedDownUpAndClearedIndependently() throws {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Simulator-only generated-image test")
        #endif
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchEnvironment=["HYDRA_TEST_ON_DEVICE":"1","HYDRA_TEST_PHOTO_FIXTURE":"1","HYDRA_TEST_ON_DEVICE_LABEL_FIXTURE":"1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Camera"].waitForExistence(timeout:15));app.tabBars.buttons["Camera"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout:10));app.buttons["syntheticPhoto"].tap()
        let analyze=app.buttons["analyzePhoto"]
        for _ in 0..<4 where !analyze.isHittable {app.swipeUp()}
        XCTAssertFalse(app.switches["photoConsent"].exists);analyze.tap()
        XCTAssertTrue(app.buttons["editRecognitionEntry"].waitForExistence(timeout:60));app.buttons["editRecognitionEntry"].tap()
        let capacity=app.textFields["photoContainerCapacity"]
        XCTAssertTrue(capacity.waitForExistence(timeout:10))
        replace(capacity,with:"355",app:app)
        XCTAssertEqual(app.staticTexts["photoVolume"].label,"355 mL")
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        replace(capacity,with:"750",app:app)
        XCTAssertEqual(app.staticTexts["photoVolume"].label,"750 mL")
        let clear=app.buttons["clearPhotoCapacity"]
        for _ in 0..<4 where !clear.isHittable {app.swipeUp()}
        clear.tap()
        XCTAssertFalse(app.buttons["savePhotoBeverage"].isEnabled)
        XCTAssertEqual(app.staticTexts["confirmedPhotoCapacity"].label,"Container size: unknown")
        replace(app.textFields["photoConsumed"],with:"240",app:app)
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="Independent container correction";screenshot.lifetime = .keepAlways;add(screenshot)
        app.buttons["Cancel"].tap()
    }

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
        let analyze=app.buttons["analyzePhoto"]
        for _ in 0..<4 where !analyze.isHittable { app.swipeUp() }
        XCTAssertFalse(app.switches["photoConsent"].exists)
        analyze.tap()
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
