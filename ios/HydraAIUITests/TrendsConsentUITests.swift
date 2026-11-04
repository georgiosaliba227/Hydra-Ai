import XCTest

/// Uses only insights_review_fixture.py, whose POST route cannot reach a provider.
final class TrendsConsentUITests: XCTestCase {
    func testReviewAndConsentResetNeverSendOnOpenOrDismiss() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let baseText = env["HYDRA_E2E_REVIEW_BACKEND_URL"], let base = URL(string: baseText),
              ["127.0.0.1", "localhost"].contains(base.host ?? ""),
              let token = env["HYDRA_E2E_API_TOKEN"] else { throw XCTSkip("Requires nonbillable review fixture") }
        let health = try get(base.appendingPathComponent("health"), token: token)
        XCTAssertEqual(health["test_provider"] as? String, "fake-no-network-review")
        XCTAssertEqual(health["billable_requests_enabled"] as? Bool, false)
        let counter = base.appendingPathComponent("__test__/trend-sends")
        let before = try get(counter, token: token)["count"] as? Int
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": baseText, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Insights"].tap(); app.buttons["insightsTrends"].tap()
        let review = app.buttons["reviewTrendsData"]
        XCTAssertTrue(review.waitForExistence(timeout: 15))
        for _ in 0..<4 where !review.isHittable { app.swipeUp() }
        review.tap()
        let consent = app.switches["trendsConsent"]
        for _ in 0..<4 where !consent.isHittable { app.swipeUp() }
        XCTAssertEqual(consent.value as? String, "0")
        XCTAssertFalse(app.buttons["trendsExplain"].isEnabled)
        consent.tap()
        XCTAssertTrue(app.buttons["trendsExplain"].isEnabled)
        app.buttons["closeTrendsReview"].tap()
        review.tap()
        for _ in 0..<4 where !consent.isHittable { app.swipeUp() }
        XCTAssertEqual(consent.value as? String, "0")
        XCTAssertFalse(app.buttons["trendsExplain"].isEnabled)
        XCTAssertEqual(try get(counter, token: token)["count"] as? Int, before)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Muse data review with default-off consent on a nonbillable fixture"
        attachment.lifetime = .keepAlways; add(attachment)
    }

    func testSavedResultShowsItsOwnWindowAndCompleteInsightsOnDemand() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let baseText = env["HYDRA_E2E_REVIEW_BACKEND_URL"], let base = URL(string: baseText),
              ["127.0.0.1", "localhost"].contains(base.host ?? ""),
              let token = env["HYDRA_E2E_API_TOKEN"] else { throw XCTSkip("Requires saved-result review fixture") }
        let health = try get(base.appendingPathComponent("health"), token: token)
        XCTAssertEqual(health["test_provider"] as? String, "fake-no-network-review")
        var components = URLComponents(url: base.appendingPathComponent("v1/wonder/trends"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "timezone", value: TimeZone.current.identifier)]
        let preview = try get(try XCTUnwrap(components.url), token: token)
        guard let latest = preview["latest"] as? [String: Any], let facts = latest["facts"] as? [String: Any],
              let through = facts["through_date"] as? String else { throw XCTSkip("Enable --saved-example on the fixture") }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": baseText, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Insights"].tap(); app.buttons["insightsTrends"].tap()
        XCTAssertTrue(app.staticTexts["trendsSummary"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["trendsSummary"].label, "You logged 500 mL over the last 7 days.")
        XCTAssertTrue(app.staticTexts["14 days through \(through)"].exists)
        XCTAssertEqual(app.staticTexts["trendsInsight-logging_consistency"].label,
                       "You logged drinks on 1 of the last 7 days. Days without logs remain unknown.")
        XCTAssertFalse(app.staticTexts["trendsInsight-beverage_mix"].exists)
        let summaryAttachment = XCTAttachment(screenshot: app.screenshot())
        summaryAttachment.name = "Simplified saved Muse summary from synthetic fixture"
        summaryAttachment.lifetime = .keepAlways; add(summaryAttachment)
        let more = app.buttons["trendsMoreInsights"]
        for _ in 0..<4 where !more.isHittable { app.swipeUp() }
        more.tap()
        XCTAssertTrue(app.staticTexts["trendsInsight-beverage_mix"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Saved Muse result and optional full insights from synthetic fixture"
        attachment.lifetime = .keepAlways; add(attachment)
    }

    private func get(_ url: URL, token: String) throws -> [String: Any] {
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let done = expectation(description: "Local fixture response")
        var bytes: Data?; var status: Int?
        URLSession.shared.dataTask(with: request) { data, response, _ in
            bytes = data; status = (response as? HTTPURLResponse)?.statusCode; done.fulfill()
        }.resume()
        wait(for: [done], timeout: 10)
        XCTAssertEqual(status, 200)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(bytes)) as? [String: Any])
    }
}
