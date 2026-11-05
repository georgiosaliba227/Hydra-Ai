import XCTest

/// Opt-in, disposable loopback backend. Exercises the real navigation; no provider calls.
final class SimplerInsightsUITests: XCTestCase {
    private func launch(largeText: Bool = false) throws -> XCUIApplication {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        if largeText { app.launchArguments = ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Insights"].tap()
        return app
    }

    private func tap(_ identifier: String, in app: XCUIApplication) {
        let button = app.buttons[identifier]
        for _ in 0..<5 where !button.isHittable { app.swipeUp() }
        XCTAssertTrue(button.waitForExistence(timeout: 5), identifier)
        button.tap()
    }

    func testWorkoutStepsValidateAndPreserveDraft() throws {
        let app = try launch()
        tap("insightsWorkout", in: app)
        XCTAssertFalse(app.textFields["Temperature, °C"].exists)
        tap("workoutContinue", in: app)
        XCTAssertTrue(app.staticTexts["workoutInputError"].exists)
        let duration = app.textFields["Duration, min"]
        duration.tap(); duration.typeText("45")
        app.toolbars.buttons["Done"].tap()
        tap("workoutContinue", in: app)
        XCTAssertTrue(app.textFields["Temperature, °C"].exists)
        XCTAssertFalse(duration.exists)
        tap("workoutContinue", in: app)
        XCTAssertTrue(app.staticTexts["workoutInputError"].exists)
        let temperature = app.textFields["Temperature, °C"]
        temperature.tap(); temperature.typeText("20")
        app.textFields["Humidity, %"].tap(); app.textFields["Humidity, %"].typeText("50")
        app.toolbars.buttons["Done"].tap()
        tap("workoutMeasurements", in: app)
        XCTAssertTrue(app.navigationBars["Past measurements"].exists)
        app.buttons["closeWorkoutMeasurements"].tap()
        tap("workoutBack", in: app)
        XCTAssertEqual(app.textFields["Duration, min"].value as? String, "45")
        tap("workoutContinue", in: app)
        tap("workoutContinue", in: app)
        XCTAssertTrue(app.staticTexts["workoutPrerequisite"].exists)
        XCTAssertFalse(app.buttons["estimateWorkout"].isEnabled)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Guided workout review with clear prerequisites"; attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testMissingMeasurementFocusesTheFirstRequiredValue() throws {
        let app = try launch()
        tap("insightsWorkout", in: app)
        app.textFields["Duration, min"].tap(); app.textFields["Duration, min"].typeText("30")
        app.toolbars.buttons["Done"].tap(); tap("workoutContinue", in: app)
        app.textFields["Temperature, °C"].tap(); app.textFields["Temperature, °C"].typeText("20")
        app.textFields["Humidity, %"].tap(); app.textFields["Humidity, %"].typeText("60")
        app.toolbars.buttons["Done"].tap(); tap("workoutMeasurements", in: app)
        tap("addWorkoutMeasurement", in: app)
        XCTAssertTrue(app.textFields["Weight before, kg"].isHittable)
        XCTAssertTrue(app.keyboards.firstMatch.exists)
    }

    func testNavigationBackReturnsToThePreviousWorkoutStep() throws {
        let app = try launch()
        tap("insightsWorkout", in: app)
        app.textFields["Duration, min"].tap(); app.textFields["Duration, min"].typeText("45")
        app.buttons["workoutKeyboardDone"].tap()
        tap("workoutContinue", in: app)
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.textFields["Duration, min"].exists)
        XCTAssertEqual(app.textFields["Duration, min"].value as? String, "45")
    }

    func testAssistantContextConsentResetsWhenLeavingTheTab() throws {
        let app = try launch()
        tap("insightsAsk", in: app)
        tap("assistantOptions", in: app)
        app.switches["assistantIncludeToday"].tap()
        XCTAssertEqual(app.switches["assistantIncludeToday"].value as? String, "1")
        tap("assistantOptions", in: app)
        app.tabBars.buttons["Today"].tap(); app.tabBars.buttons["Insights"].tap()
        if app.buttons["insightsAsk"].exists { tap("insightsAsk", in: app) }
        tap("assistantOptions", in: app)
        XCTAssertEqual(app.switches["assistantIncludeToday"].value as? String, "0")
    }

    func testPersonalEstimateRequiresConsentAndLeavingClearsMeasurements() throws {
        let app = try launch()
        tap("insightsWorkout", in: app)
        func fill(_ label: String, _ value: String) {
            let field = app.textFields[label]
            for _ in 0..<7 where !field.isHittable { app.swipeUp() }
            field.tap(); field.typeText(value)
            let done = app.buttons["workoutKeyboardDone"].firstMatch
            XCTAssertTrue(done.waitForExistence(timeout: 5)); done.tap()
            XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        }
        fill("Duration, min", "30")
        tap("workoutContinue", in: app)
        fill("Temperature, °C", "20"); fill("Humidity, %", "60")
        app.switches["workoutComparable"].tap()
        tap("workoutMeasurements", in: app)
        for (label, value) in [("Weight before, kg", "70"), ("Weight after, kg", "69"),
                               ("Drank during, mL", "400"), ("Urine during, mL", "0"),
                               ("Measured duration, min", "60"), ("Each weighing ±, kg", "0.05"),
                               ("Amount drunk ±, mL", "10"), ("Urine ±, mL", "0"), ("Duration ±, min", "0")] {
            fill(label, value)
        }
        let protocolToggle = app.switches["Comparable dry weighing; all intake and urine recorded"]
        for _ in 0..<4 where !protocolToggle.isHittable { app.swipeUp() }
        let protocolControl = protocolToggle.switches.firstMatch
        XCTAssertTrue(protocolControl.exists); protocolControl.tap()
        XCTAssertEqual(protocolToggle.value as? String, "1")
        tap("addWorkoutMeasurement", in: app)
        XCTAssertTrue(app.navigationBars["Past measurements"].waitForNonExistence(timeout: 5))
        tap("workoutContinue", in: app)
        let consent = app.switches["workoutCalibrationConsent"]
        for _ in 0..<4 where !consent.isHittable { app.swipeUp() }
        XCTAssertEqual(consent.value as? String, "0")
        XCTAssertFalse(app.buttons["estimateWorkout"].isEnabled)
        consent.tap()
        tap("estimateWorkout", in: app)
        XCTAssertTrue(app.staticTexts["workoutPrediction"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["workoutPrediction"].label.contains("700"))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Personal estimate from synthetic measurements with uncertainty"
        attachment.lifetime = .keepAlways; add(attachment)
        tap("editWorkout", in: app)
        XCTAssertFalse(app.staticTexts["workoutPrediction"].exists)
        fill("Duration, min", "1")
        let editedDuration = try XCTUnwrap(app.textFields["Duration, min"].value as? String)
        XCTAssertNotEqual(Double(editedDuration), 30)
        tap("workoutContinue", in: app); tap("workoutContinue", in: app)
        for _ in 0..<4 where !consent.isHittable { app.swipeUp() }
        XCTAssertEqual(consent.value as? String, "0", "An edited estimate needs fresh processing consent")
        XCTAssertFalse(app.buttons["estimateWorkout"].isEnabled)
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.textFields["Temperature, °C"].exists)
        XCTAssertTrue(app.buttons["workoutMeasurements"].label.contains("1 in this session"))
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertEqual(app.textFields["Duration, min"].value as? String, editedDuration)
        app.navigationBars.buttons.firstMatch.tap()
        tap("insightsWorkout", in: app)
        XCTAssertEqual(app.textFields["Duration, min"].value as? String, "—")
        XCTAssertFalse(app.staticTexts["workoutPrediction"].exists)
    }

    func testTrendsReviewIsExplicitAndMockOffersNoSend() throws {
        // This case needs a log regardless of whether delete-all ran earlier.
        let env = ProcessInfo.processInfo.environment
        guard let backend = env["HYDRA_E2E_BACKEND_URL"], let base = URL(string: backend),
              let token = env["HYDRA_E2E_API_TOKEN"] else { throw XCTSkip("Requires local synthetic-data backend") }
        var request = URLRequest(url: base.appendingPathComponent("v1/beverages"))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(UUID().uuidString, forHTTPHeaderField: "Idempotency-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["category": "water", "consumed_ml": 500,
            "source": "manual", "timezone": "UTC", "consumed_at": ISO8601DateFormatter().string(from: .now)] as [String: Any])
        let logged = expectation(description: "Independent synthetic trends fixture")
        var status = 0
        URLSession.shared.dataTask(with: request) { _, response, _ in
            status = (response as? HTTPURLResponse)?.statusCode ?? 0; logged.fulfill()
        }.resume()
        wait(for: [logged], timeout: 10)
        XCTAssertEqual(status, 201)
        let app = try launch()
        tap("insightsTrends", in: app)
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "trendsPreview").firstMatch.exists)
        tap("reviewTrendsData", in: app)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "trendsPreview").firstMatch.exists)
        XCTAssertFalse(app.buttons["trendsExplain"].exists)
        tap("trendsCompletePayload", in: app)
        XCTAssertTrue(app.staticTexts["Daily totals & drink counts"].exists)
        app.buttons["closeTrendsReview"].tap()
        XCTAssertFalse(app.staticTexts["Daily totals & drink counts"].exists)
        tap("reviewTrendsData", in: app)
        XCTAssertFalse(app.staticTexts["Daily totals & drink counts"].exists)
    }

    func testAssistantKeepsOptionalChoicesAndSourcesBehindDisclosures() throws {
        let app = try launch()
        tap("insightsAsk", in: app)
        XCTAssertFalse(app.switches["assistantIncludeToday"].exists)
        tap("assistantOptions", in: app)
        XCTAssertTrue(app.switches["assistantIncludeToday"].exists)
        XCTAssertEqual(app.switches["assistantIncludeToday"].value as? String, "0")
        app.switches["assistantIncludeToday"].tap()
        app.switches["assistantRecordedWonder"].tap()
        XCTAssertEqual(app.switches["assistantIncludeToday"].value as? String, "0")
        XCTAssertFalse(app.switches["assistantIncludeToday"].isEnabled)
        XCTAssertFalse(app.buttons["assistantAsk"].isEnabled)
        XCTAssertTrue(app.staticTexts["assistantRecordedMode"].exists)
        app.switches["assistantRecordedWonder"].tap()
        tap("assistantOptions", in: app)
        tap("suggested-coffee_counts", in: app)
        XCTAssertTrue(app.staticTexts["assistantAnswer-coffee_caffeine"].waitForExistence(timeout: 10))
        let source = app.buttons["Killer et al., 2014: coffee and fluid balance"]
        XCTAssertFalse(source.exists)
        tap("assistantSources-coffee_caffeine", in: app)
        XCTAssertTrue(source.waitForExistence(timeout: 5))
        XCTAssertTrue(source.isEnabled)
    }

    func testAccessibilityTextKeepsInsightsAndWorkoutActionsReachable() throws {
        let app = try launch(largeText: true)
        var attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Insights at the largest accessibility text size"
        attachment.lifetime = .keepAlways; add(attachment)
        tap("insightsWorkout", in: app)
        let duration = app.textFields["Duration, min"]
        for _ in 0..<5 where !duration.isHittable { app.swipeUp() }
        duration.tap(); duration.typeText("30"); app.toolbars.buttons["Done"].tap()
        tap("workoutContinue", in: app)
        let temperature = app.textFields["Temperature, °C"]
        for _ in 0..<5 where !temperature.isHittable { app.swipeUp() }
        XCTAssertTrue(temperature.isHittable)
        attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Workout conditions at the largest accessibility text size"
        attachment.lifetime = .keepAlways; add(attachment)
        try app.performAccessibilityAudit { issue in
            let frame = issue.element?.frame ?? .zero
            let offscreen = !frame.isEmpty && !app.windows.firstMatch.frame.intersects(frame)
            let underBars = [app.navigationBars.firstMatch, app.tabBars.firstMatch]
                .contains { $0.exists && $0.frame.intersects(frame) }
            return issue.element == nil || frame.isEmpty || offscreen || underBars
                || issue.element?.isEnabled == false || issue.compactDescription.contains("nearly passed")
                || issue.compactDescription.contains("partially unsupported")
        }
    }

    func testTodayHasOneInsightsEntry() throws {
        let app = try launch()
        app.tabBars.buttons["Today"].tap()
        tap("exploreInsights", in: app)
        XCTAssertTrue(app.buttons["insightsWorkout"].exists)
        XCTAssertTrue(app.buttons["insightsTrends"].exists)
        XCTAssertTrue(app.buttons["insightsAsk"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Simplified Insights navigation"
        attachment.lifetime = .keepAlways; add(attachment)
    }
}
