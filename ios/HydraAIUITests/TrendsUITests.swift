import XCTest

/// Opt-in: against a LOCAL mock backend, the Trends screen previews exactly what would be sent and offers no live request.
final class TrendsUITests: XCTestCase {
    func testTrendsPreviewShowsTheDataWithoutSendingIt() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"], let base = URL(string: backend),
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        try logSyntheticDrink(base: base, token: token)
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let link = app.buttons["wonderTrends"]
        for _ in 0..<4 where !(link.waitForExistence(timeout: 2) && link.isHittable) { app.swipeUp() }
        link.tap()
        let preview = app.descendants(matching: .any).matching(identifier: "trendsPreview").firstMatch
        XCTAssertTrue(preview.waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["What would be sent to Meta"].exists)
        XCTAssertFalse(app.buttons["trendsExplain"].exists)  // mock backend: no live Wonder, nothing to send
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Trends preview on a mock backend"; attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func logSyntheticDrink(base: URL, token: String) throws {
        var request = URLRequest(url: base.appendingPathComponent("v1/beverages"))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(UUID().uuidString, forHTTPHeaderField: "Idempotency-Key")
        let formatter = ISO8601DateFormatter()
        let body: [String: Any] = ["category": "water", "consumed_ml": 500, "source": "manual", "timezone": "UTC",
                                   "consumed_at": formatter.string(from: Date().addingTimeInterval(-3600))]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let done = expectation(description: "synthetic drink logged")
        var status = 0
        URLSession.shared.dataTask(with: request) { _, response, _ in
            status = (response as? HTTPURLResponse)?.statusCode ?? 0
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 10)
        XCTAssertEqual(status, 201)
    }
}
