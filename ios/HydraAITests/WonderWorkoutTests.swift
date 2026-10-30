import Foundation
import XCTest
@testable import HydraAI

/// "Wonder explains this workout" and the workout-screen autofill. Fixtures are the JSON examples in
/// docs/architecture/WONDER_WORKOUT_API.md; no network (stub services and FixtureURLProtocol only).
final class WonderWorkoutTests: XCTestCase {
    // MARK: Fixtures from WONDER_WORKOUT_API.md

    /// `POST /v1/wonder/workout/preview` response, facts for 75 hot, high-intensity minutes against 4 runs.
    static let factsJSON = #"{"version":"wonder-workout-facts-v1","timezone":"Europe/Paris","planned":{"activity":"running","intensity":"high","time_of_day":"evening","duration_minutes":75,"temperature_c":31,"humidity_percent":60,"conditions_confirmed":false},"history":{"sessions":4,"activity_sessions":4,"matching_sessions":0,"weigh_in_sessions":2,"typical_duration_minutes":45,"typical_temperature_c":22,"typical_humidity_percent":55,"measured_loss_ml":800},"estimate":{"status":"insufficient_data","value_ml":null,"lower_ml":null,"upper_ml":null,"sample_count":0,"missing_inputs":["confirmed_comparable_conditions","usable_measurements_with_error_bounds"]},"comparison":{"duration":"longer","temperature":"hotter","humidity":"similar","estimate":null},"suggested_measurement":"weigh_this_workout","applicable_insights":["duration_vs_typical","weather_vs_typical","comparable_history","missing_information","refine_estimate"]}"#
    static let digest = "fa6dfd6b2378ce12b206da62fb691d7479c2b418e9db2203b1c71178275084f7"
    static var previewJSON: String {
        #"{"version":"wonder-workout-v1","facts":"# + factsJSON + #","explainable":true,"payload_sha256":"\#(digest)","input_bound_tokens":4286,"worst_case_micro_usd":58104,"live_available":true,"account_id":"aminealichaouche","saved":null}"#
    }
    /// The documented `result` with `"facts": the previewed facts, exactly`.
    static var resultJSON: String {
        #"{"version":"wonder-workout-v1","facts":"# + factsJSON + #","payload_sha256":"\#(digest)","summary":"This workout is longer than your typical run (75 vs 45 minutes) and hotter than your typical run (31 °C vs 22 °C).","summary_template":"This workout is {duration_comparison} and {temperature_comparison}.","insights":[{"id":"comparable_history","title":"Your previous sessions","template":"Hydra compared it with {previous_sessions}, including {weigh_ins}.","text":"Hydra compared it with 4 previous runs, including 2 of your 4 previous runs with a complete before-and-after weigh-in."},{"id":"missing_information","title":"What is missing","template":"Hydra has no estimate yet; it is missing {missing_information}.","text":"Hydra has no estimate yet; it is missing your confirmation that this workout's conditions match your earlier sessions and previous weigh-ins at the same intensity, temperature and humidity, with their measurement error bounds."},{"id":"refine_estimate","title":"What would refine it","template":"Recording {suggested_measurement} would help refine the estimate.","text":"Recording your weight before and after this workout, plus what you drink and any urine during it would help refine the estimate."}],"generated_at":"2026-10-30T01:04:52.988795+00:00","provenance":{"mode":"meta_live","provider":"Meta","model":"muse-wonder-1.0","account_id":"aminealichaouche","attempt_id":"7938cc7c-896c-4da0-9cf8-f013ddad8db1","text_origin":"muse_wonder_checked","numbers_checked_against":"facts"},"provider_observations":{"latency_ms":0,"input_tokens":1900,"output_tokens":600,"usage_derived_cost_micro_usd":19600,"billed_cost_usd":null},"limitations":["Wellness information, not medical advice.","Muse Wonder wrote the wording; every number was computed and filled in by Hydra from your entries.","The estimate is of workout fluid loss only. It is not a drinking target or a daily fluid requirement.","Temperature and humidity are context only; the estimate applies no weather adjustment.","Heart rate is not used, and Hydra does not infer dehydration."]}"#
    }
    static var responseJSON: String { #"{"replayed":false,"saved":true,"result":"# + resultJSON + "}" }
    static let staleJSON = #"{"code": "workout_preview_stale", "message": "Your planned workout or history changed since the preview. Review the new preview first.", "request_id": "68b7a294-e4a6-49e8-8706-f25a83778dba", "retryable": true}"#
    /// The documented estimated variant (same history, planned moderate at 22 °C / 55 %, confirmed).
    static let estimatedFactsJSON = #"{"version":"wonder-workout-facts-v1","timezone":"Europe/Paris","planned":{"activity":"running","intensity":"moderate","time_of_day":"evening","duration_minutes":75,"temperature_c":22,"humidity_percent":55,"conditions_confirmed":true},"history":{"sessions":4,"activity_sessions":4,"matching_sessions":4,"weigh_in_sessions":2,"typical_duration_minutes":45,"typical_temperature_c":22,"typical_humidity_percent":55,"measured_loss_ml":800},"estimate":{"status":"estimated","value_ml":1417,"lower_ml":1125,"upper_ml":1750,"sample_count":2,"missing_inputs":[]},"comparison":{"duration":"longer","temperature":"similar","humidity":"similar","estimate":"above"},"suggested_measurement":"repeat_weigh_in","applicable_insights":["duration_vs_typical","weather_vs_typical","comparable_history","estimate","estimate_vs_previous","refine_estimate"]}"#

    private func object(_ json: String) -> [String: Any] {
        try! JSONSerialization.jsonObject(with: Data(json.utf8)) as! [String: Any]
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String, _ change: (inout [String: Any]) -> Void = { _ in }) throws -> T {
        var value = object(json)
        change(&value)
        return try JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: value))
    }

    /// The doc's planned workout, built by the screen's own request builder.
    static func plannedRequest(samples: [WorkoutForecastRequest.Sample] = [], consent: Bool = false) throws -> WorkoutForecastRequest {
        var draft = WorkoutDraft()
        draft.activity = "running"; draft.intensity = "high"; draft.duration = "75"
        draft.temperature = "31"; draft.humidity = "60"; draft.consent = consent
        draft.startsAt = Date.now.addingTimeInterval(86_400)
        return try draft.personalRequest(samples: samples, timezone: "Europe/Paris")
    }

    // MARK: Request encoding

    func testExplanationRequestIsTheEstimateRequestPlusHashAndLiteralConsent() throws {
        let forecast = try Self.plannedRequest()
        let explain = WorkoutExplanationRequest(forecast: forecast, payload_sha256: Self.digest)
        let sent = object(String(decoding: try JSONEncoder().encode(explain), as: UTF8.self))
        var estimate = object(String(decoding: try JSONEncoder().encode(forecast), as: UTF8.self))

        XCTAssertEqual(Set(sent.keys), Set(estimate.keys).union(["payload_sha256", "consent_to_send"]))
        XCTAssertEqual(sent["payload_sha256"] as? String, Self.digest)
        XCTAssertTrue(String(decoding: try JSONEncoder().encode(explain), as: UTF8.self).contains(#""consent_to_send":true"#))
        XCTAssertEqual(sent["mode"] as? String, "personal")
        XCTAssertEqual(sent["timezone"] as? String, "Europe/Paris")
        XCTAssertEqual(sent["calibration_processing_consent"] as? Bool, false)
        XCTAssertEqual((sent["samples"] as? [Any])?.count, 0)
        let exercise = try XCTUnwrap(sent["exercise"] as? [String: Any])
        XCTAssertEqual(exercise["duration_minutes"] as? Double, 75)
        XCTAssertEqual(exercise["comparable_conditions_confirmed"] as? Bool, false)
        XCTAssertNil(exercise["actual"], "A planned workout carries no completed measurement")
        let conditions = try XCTUnwrap(exercise["conditions"] as? [String: Any])
        XCTAssertEqual(conditions["activity"] as? String, "running")
        XCTAssertEqual(conditions["intensity"] as? String, "high")
        XCTAssertEqual(conditions["temperature_c"] as? Double, 31)
        XCTAssertEqual(conditions["humidity_percent"] as? Double, 60)
        // Everything else is byte-for-byte the estimate request, so the backend recomputes the previewed facts.
        estimate["payload_sha256"] = Self.digest; estimate["consent_to_send"] = true
        XCTAssertEqual(NSDictionary(dictionary: sent), NSDictionary(dictionary: estimate))
        // No Apple Health fields ever reach the request.
        let text = String(decoding: try JSONEncoder().encode(explain), as: UTF8.self)
        for field in ["heart", "energy", "kcal", "bpm", "wearable"] { XCTAssertFalse(text.lowercased().contains(field), field) }
    }

    func testOnlyAPersonalRequestWithAPlannedWorkoutCanBeExplained() throws {
        XCTAssertThrowsError(try WorkoutForecastRequest.demonstration(timezone: "Europe/Paris").validateForWonder())
        XCTAssertNoThrow(try Self.plannedRequest().validateForWonder())
    }

    // MARK: Response decoding (doc fixtures)

    func testDocumentedPreviewDecodesAndValidates() throws {
        let preview = try decode(WorkoutWonderPreview.self, Self.previewJSON)
        XCTAssertNoThrow(try preview.validate(request: Self.plannedRequest()))
        XCTAssertTrue(preview.explainable)
        XCTAssertEqual(preview.payload_sha256, Self.digest)
        XCTAssertEqual(preview.worst_case_micro_usd, 58104)
        XCTAssertEqual(preview.facts.history.weigh_in_sessions, 2)
        XCTAssertEqual(preview.facts.history.measured_loss_ml, 800)
        XCTAssertEqual(preview.facts.estimate.missing_inputs, ["confirmed_comparable_conditions", "usable_measurements_with_error_bounds"])
        XCTAssertEqual(WorkoutForecastView.estimateText(preview.facts.estimate), "No estimate yet")
        XCTAssertEqual(WorkoutForecastView.plannedText(preview.facts.planned),
                       "75 min of high-intensity running in the evening · 31 °C · 60% humidity · conditions not confirmed as matching")
        XCTAssertEqual(WorkoutForecastView.typicalText(preview.facts.history), "45 min · 22 °C · 55% humidity")
        let night = WorkoutFacts.Planned(activity: "strength", intensity: nil, time_of_day: "night", duration_minutes: 30,
                                         temperature_c: nil, humidity_percent: nil, conditions_confirmed: true)
        XCTAssertEqual(WorkoutForecastView.plannedText(night), "30 min of strength training at night · conditions confirmed as matching")
    }

    func testPreviewMustMatchTheRequestAndBeConsistent() throws {
        let request = try Self.plannedRequest()
        let broken: [(inout [String: Any]) -> Void] = [
            { $0["payload_sha256"] = NSNull() },                          // explainable without a hash
            { $0["account_id"] = "someone-else" },
            { $0["account_id"] = NSNull() },                              // live without an account
            { $0["version"] = "wonder-workout-v0" },
            { var f = $0["facts"] as! [String: Any]; f["timezone"] = "America/New_York"; $0["facts"] = f },
            { var f = $0["facts"] as! [String: Any]; var p = f["planned"] as! [String: Any]; p["activity"] = "cycling"; f["planned"] = p; $0["facts"] = f },
            { var f = $0["facts"] as! [String: Any]; var h = f["history"] as! [String: Any]; h["matching_sessions"] = 9; f["history"] = h; $0["facts"] = f },
            { var f = $0["facts"] as! [String: Any]; f["applicable_insights"] = ["diagnosis"]; $0["facts"] = f },
        ]
        for change in broken {
            XCTAssertThrowsError(try decode(WorkoutWonderPreview.self, Self.previewJSON, change).validate(request: request))
        }
        // Mock backend: no live Wonder, no account; still a valid preview.
        let mock = try decode(WorkoutWonderPreview.self, Self.previewJSON) { $0["live_available"] = false; $0["account_id"] = NSNull() }
        XCTAssertNoThrow(try mock.validate(request: request))
    }

    func testDocumentedResultDecodesWithTitlesAndFixedLimitations() throws {
        let response = try decode(WorkoutExplanationResponse.self, Self.responseJSON)
        let result = response.result
        XCTAssertNoThrow(try result.validate())
        XCTAssertFalse(response.replayed)
        XCTAssertTrue(response.saved)
        XCTAssertEqual(result.summary, "This workout is longer than your typical run (75 vs 45 minutes) and hotter than your typical run (31 °C vs 22 °C).")
        XCTAssertEqual(result.insights.map(\.title), ["Your previous sessions", "What is missing", "What would refine it"])
        XCTAssertEqual(result.limitations.count, 5)
        XCTAssertEqual(result.limitations.last, "Heart rate is not used, and Hydra does not infer dehydration.")
        XCTAssertEqual(result.inputTokens, 1900)
        XCTAssertEqual(result.outputTokens, 600)
        XCTAssertEqual(result.costUSD, 0.0196)
        XCTAssertEqual(result.provenance.attempt_id, "7938cc7c-896c-4da0-9cf8-f013ddad8db1")
        XCTAssertEqual(result.facts, try decode(WorkoutFacts.self, Self.factsJSON))
    }

    func testTamperedResultsAreRejected() throws {
        let tampering: [(inout [String: Any]) -> Void] = [
            { var p = $0["provenance"] as! [String: Any]; p["model"] = "muse-spark-1.3"; $0["provenance"] = p },
            { var p = $0["provenance"] as! [String: Any]; p["account_id"] = "someone-else"; $0["provenance"] = p },
            { var p = $0["provenance"] as! [String: Any]; p["text_origin"] = "reviewed_text"; $0["provenance"] = p },
            { var o = $0["provider_observations"] as! [String: Any]; o["billed_cost_usd"] = 0.01; $0["provider_observations"] = o },
            { $0["insights"] = [] as [Any] },
            { $0["insights"] = [["id": "estimate", "title": "The estimate", "text": "No estimate was computed."]] },  // not applicable
            { $0["insights"] = [["id": "refine_estimate", "title": "Drink more", "text": "Recording helps."]] },        // wrong title
            { $0["limitations"] = [] as [Any] },
            { $0["version"] = "wonder-trends-v1" },
        ]
        for change in tampering {
            XCTAssertThrowsError(try decode(WonderWorkout.self, Self.resultJSON, change).validate())
        }
    }

    func testDocumentedEstimatedFactsShowAWholeMillilitreRange() throws {
        let facts = try decode(WorkoutFacts.self, Self.estimatedFactsJSON)
        XCTAssertTrue(facts.isValid)
        XCTAssertEqual(WorkoutForecastView.estimateText(facts.estimate), "1,125–1,750 mL of fluid loss (not a drinking target)")
    }

    func testErrorEnvelopeIsParsed() {
        let stale = WonderRequestError(status: 409, body: Data(Self.staleJSON.utf8))
        XCTAssertEqual(stale, WonderRequestError(status: 409, code: "workout_preview_stale"))
        let unresolved = WonderRequestError(status: 502, body: Data(#"{"code":"wonder_attempt_unresolved","message":"x","request_id":"r","retryable":false,"attempt_id":"7938cc7c-896c-4da0-9cf8-f013ddad8db1"}"#.utf8))
        XCTAssertEqual(unresolved.attemptId, "7938cc7c-896c-4da0-9cf8-f013ddad8db1")
        XCTAssertNil(WonderRequestError(status: 500, body: Data("not json".utf8)).code)
    }

    func testEveryErrorCodeHasAClearMessage() {
        let message = { (code: String, status: Int) in WonderWorkoutController.message(for: .init(status: status, code: code)) }
        XCTAssertEqual(message("workout_insufficient_history", 422).hasPrefix("Log a previous session of this activity first"), true)
        XCTAssertTrue(message("workout_preview_stale", 409).contains("changed since the preview"))
        XCTAssertTrue(message("wonder_blocked", 409).contains("spending safeguard"))
        XCTAssertTrue(message("wonder_blocked", 409).contains("Nothing was sent or charged"))
        XCTAssertTrue(message("wonder_busy", 409).contains("Try again in a moment"))
        XCTAssertTrue(message("wonder_unavailable", 503).contains("isn't set up on this backend"))
        XCTAssertTrue(message("invalid_request", 422).contains("Check the fields above"))
        let unresolved = WonderWorkoutController.message(for: .init(status: 502, code: "wonder_attempt_unresolved", attemptId: "7938cc7c-896c-4da0-9cf8-f013ddad8db1"))
        XCTAssertTrue(unresolved.contains("Don't try again"))
        XCTAssertTrue(unresolved.contains("7938cc7c-896c-4da0-9cf8-f013ddad8db1"))
        XCTAssertTrue(WonderWorkoutController.message(for: .init(status: 502)).contains("Don't try again"))
        XCTAssertTrue(WonderWorkoutController.message(for: .init(status: 500)).contains("unavailable"))
    }

    // MARK: Controller

    @MainActor func testNothingIsSentWithoutConsentAndTheSamePayloadIsSentOnce() async throws {
        let service = StubWonderService(preview: Self.previewJSON, response: Self.responseJSON)
        let controller = WonderWorkoutController()
        let request = try Self.plannedRequest()
        await controller.loadPreview(request, service: service)
        XCTAssertEqual(controller.state, .loaded)
        XCTAssertTrue(controller.canOffer)
        XCTAssertNil(controller.result)

        await controller.explain(consent: false, service: service)
        var sent = await service.explained
        XCTAssertTrue(sent.isEmpty, "No Meta request without consent")
        XCTAssertNil(controller.result)

        await controller.explain(consent: true, service: service)
        sent = await service.explained
        XCTAssertEqual(sent.map(\.payload_sha256), [Self.digest])
        XCTAssertEqual(sent.first?.consent_to_send, true)
        XCTAssertEqual(sent.first?.forecast.exercise?.event_id, request.exercise?.event_id, "Explains exactly the previewed request")
        XCTAssertEqual(controller.result?.insights.count, 3)
        XCTAssertTrue(controller.alreadyExplained)
        XCTAssertFalse(controller.canOffer)
        XCTAssertFalse(controller.replayed)

        await controller.explain(consent: true, service: service)
        let previews = await service.previewed
        sent = await service.explained
        XCTAssertEqual(sent.count, 1, "The same payload is never sent twice")
        XCTAssertEqual(previews, 1)
    }

    @MainActor func testMockBackendOffersNothingToSend() async throws {
        let mock = try JSONSerialization.data(withJSONObject: { () -> [String: Any] in
            var value = object(Self.previewJSON); value["live_available"] = false; value["account_id"] = NSNull(); return value
        }())
        let service = StubWonderService(preview: String(decoding: mock, as: UTF8.self), response: Self.responseJSON)
        let controller = WonderWorkoutController()
        await controller.loadPreview(try Self.plannedRequest(), service: service)
        XCTAssertNotNil(controller.preview)
        XCTAssertFalse(controller.canOffer)
        await controller.explain(consent: true, service: service)
        let sent = await service.explained
        XCTAssertTrue(sent.isEmpty)
    }

    @MainActor func testNoHistoryIsNotExplainable() async throws {
        let none = #"{"version":"wonder-workout-v1","facts":{"version":"wonder-workout-facts-v1","timezone":"Europe/Paris","planned":{"activity":"running","intensity":"high","time_of_day":"evening","duration_minutes":75,"temperature_c":31,"humidity_percent":60,"conditions_confirmed":false},"history":{"sessions":0,"activity_sessions":0,"matching_sessions":0,"weigh_in_sessions":0,"typical_duration_minutes":null,"typical_temperature_c":null,"typical_humidity_percent":null,"measured_loss_ml":null},"estimate":{"status":"insufficient_data","value_ml":null,"lower_ml":null,"upper_ml":null,"sample_count":0,"missing_inputs":["confirmed_comparable_conditions","usable_measurements_with_error_bounds"]},"comparison":{"duration":null,"temperature":null,"humidity":null,"estimate":null},"suggested_measurement":"weigh_this_workout","applicable_insights":[]},"explainable":false,"payload_sha256":null,"input_bound_tokens":null,"worst_case_micro_usd":null,"live_available":true,"account_id":"aminealichaouche","saved":null}"#
        let service = StubWonderService(preview: none, response: Self.responseJSON)
        let controller = WonderWorkoutController()
        await controller.loadPreview(try Self.plannedRequest(), service: service)
        XCTAssertEqual(controller.preview?.explainable, false)
        XCTAssertFalse(controller.canOffer)
        await controller.explain(consent: true, service: service)
        let sent = await service.explained
        XCTAssertTrue(sent.isEmpty)
    }

    @MainActor func testSavedExplanationReplaysWithoutAsking() async throws {
        let saved = Self.previewJSON.replacingOccurrences(of: #""saved":null"#, with: #""saved":"# + Self.resultJSON)
        let service = StubWonderService(preview: saved, response: Self.responseJSON)
        let controller = WonderWorkoutController()
        await controller.loadPreview(try Self.plannedRequest(), service: service)
        XCTAssertEqual(controller.result?.payload_sha256, Self.digest)
        XCTAssertTrue(controller.replayed)
        XCTAssertTrue(controller.alreadyExplained)
        XCTAssertFalse(controller.canOffer)
        await controller.explain(consent: true, service: service)
        let sent = await service.explained
        XCTAssertTrue(sent.isEmpty)
    }

    @MainActor func testUnresolvedAttemptIsNeverOfferedAgain() async throws {
        let service = StubWonderService(preview: Self.previewJSON, response: Self.responseJSON,
                                        error: .init(status: 502, code: "wonder_attempt_unresolved", attemptId: "7938cc7c-896c-4da0-9cf8-f013ddad8db1"))
        let controller = WonderWorkoutController()
        let request = try Self.plannedRequest()
        await controller.loadPreview(request, service: service)
        await controller.explain(consent: true, service: service)
        XCTAssertNil(controller.result)
        XCTAssertTrue(controller.explainError?.contains("Don't try again") == true)
        XCTAssertFalse(controller.canOffer)
        // Even after a fresh preview of the same payload.
        await controller.loadPreview(request, service: service)
        XCTAssertFalse(controller.canOffer)
        await controller.explain(consent: true, service: service)
        let sent = await service.explained
        XCTAssertEqual(sent.count, 1)
    }

    @MainActor func testStalePreviewIsRefreshedAndConsentAskedAgain() async throws {
        let service = StubWonderService(preview: Self.previewJSON, response: Self.responseJSON,
                                        error: .init(status: 409, code: "workout_preview_stale"))
        let controller = WonderWorkoutController()
        await controller.loadPreview(try Self.plannedRequest(), service: service)
        await controller.explain(consent: true, service: service)
        let previews = await service.previewed
        XCTAssertEqual(previews, 2, "A stale preview is computed again (not billable)")
        XCTAssertEqual(controller.explainError, WonderWorkoutController.message(for: .init(status: 409, code: "workout_preview_stale")))
        XCTAssertNotNil(controller.preview)
        XCTAssertNil(controller.result)
    }

    @MainActor func testOtherRefusalsMapToTheirMessages() async throws {
        for code in ["workout_insufficient_history", "wonder_blocked", "wonder_busy", "wonder_unavailable"] {
            let error = WonderRequestError(status: code == "wonder_unavailable" ? 503 : 409, code: code)
            let service = StubWonderService(preview: Self.previewJSON, response: Self.responseJSON, error: error)
            let controller = WonderWorkoutController()
            await controller.loadPreview(try Self.plannedRequest(), service: service)
            await controller.explain(consent: true, service: service)
            XCTAssertEqual(controller.explainError, WonderWorkoutController.message(for: error), code)
            XCTAssertNil(controller.result, code)
        }
    }

    @MainActor func testLateReplyAfterInvalidateIsDiscarded() async throws {
        let service = StubWonderService(preview: Self.previewJSON, response: Self.responseJSON)
        let controller = WonderWorkoutController()
        await controller.loadPreview(try Self.plannedRequest(), service: service)
        controller.invalidate()
        XCTAssertNil(controller.preview)
        await controller.explain(consent: true, service: service)
        let sent = await service.explained
        XCTAssertTrue(sent.isEmpty, "Nothing to explain once the workout changed")
    }

    // MARK: HTTP service

    func testServiceUsesBothEndpointsAndReadsErrorCodes() async throws {
        let options = URLSessionConfiguration.ephemeral
        options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(
            configuration: APIConfiguration(baseURL: "http://127.0.0.1:8013", token: String(repeating: "x", count: 40), offline: false),
            session: URLSession(configuration: options))
        defer { FixtureURLProtocol.handler = nil }
        let request = try Self.plannedRequest()
        var paths: [String] = []
        var bodies: [[String: Any]] = []
        FixtureURLProtocol.handler = { urlRequest in
            paths.append(urlRequest.url!.path)
            let body = urlRequest.httpBody ?? urlRequest.httpBodyStream.map { stream -> Data in
                stream.open(); defer { stream.close() }
                var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: 4096); if n <= 0 { break }; data.append(buffer, count: n) }
                return data
            } ?? Data()
            bodies.append((try? JSONSerialization.jsonObject(with: body)) as? [String: Any] ?? [:])
            XCTAssertEqual(urlRequest.httpMethod, "POST")
            XCTAssertEqual(urlRequest.value(forHTTPHeaderField: "Authorization"), "Bearer " + String(repeating: "x", count: 40))
            return urlRequest.url!.path.hasSuffix("/preview") ? (200, Data(Self.previewJSON.utf8)) : (200, Data(Self.responseJSON.utf8))
        }
        let preview = try await service.wonderWorkoutPreview(request)
        XCTAssertEqual(preview.payload_sha256, Self.digest)
        let response = try await service.explainWorkout(.init(forecast: request, payload_sha256: Self.digest))
        XCTAssertEqual(response.result.summary.prefix(15), "This workout is")
        XCTAssertEqual(paths, ["/v1/wonder/workout/preview", "/v1/wonder/workout"])
        XCTAssertNil(bodies[0]["consent_to_send"], "The preview never carries consent")
        XCTAssertEqual(bodies[1]["consent_to_send"] as? Bool, true)
        XCTAssertEqual(bodies[1]["payload_sha256"] as? String, Self.digest)

        FixtureURLProtocol.handler = { _ in (409, Data(Self.staleJSON.utf8)) }
        do {
            _ = try await service.explainWorkout(.init(forecast: request, payload_sha256: Self.digest))
            XCTFail("Expected a refusal")
        } catch let error as WonderRequestError {
            XCTAssertEqual(error, WonderRequestError(status: 409, code: "workout_preview_stale"))
        }
        FixtureURLProtocol.handler = { _ in (200, Data(Self.responseJSON.replacingOccurrences(of: Self.digest, with: String(repeating: "0", count: 64)).utf8)) }
        do {
            _ = try await service.explainWorkout(.init(forecast: request, payload_sha256: Self.digest))
            XCTFail("A result for another payload must be rejected")
        } catch ServiceError.invalidResponse {
        } catch { XCTFail("Unexpected \(error)") }
    }

    // MARK: Formatting

    func testWorkoutNumbersAreWholeMillilitres() {
        XCTAssertEqual(HydraFormat.milliliterRange(0, 683.3), "0–683 mL")
        XCTAssertEqual(HydraFormat.milliliters(683.6), "684")
        XCTAssertEqual(WorkoutForecastView.factorText(key: "estimated_loss_ml", .number(683.33)), "683 mL")
        XCTAssertEqual(WorkoutForecastView.factorText(key: "temperature_c", .number(22.5)), "22.5")
    }

    func testAutofilledTextParsesInAnyLocale() throws {
        var draft = WorkoutDraft()
        draft.applyWeather(temperatureC: 22.5, humidityPercent: 55)
        XCTAssertEqual(draft.temperature, "22.5")
        XCTAssertEqual(draft.humidity, "55")
        draft.applyWorkout(activity: "cycling", intensity: nil, durationMinutes: 1250)
        XCTAssertEqual(draft.duration, "1250", "No grouping separator the parser can't read")
        draft.temperature = "22,5"  // typed with a comma decimal keyboard
        XCTAssertEqual(try draft.conditions().temperature_c, 22.5)
    }
}

// MARK: - Autofill on the workout screen

/// Counts location lookups; never touches CoreLocation.
@MainActor private final class CountingLocation: ApproximateLocationProvider {
    private(set) var calls = 0
    func approximateCoordinate() async throws -> RoundedCoordinate {
        calls += 1
        return try RoundedCoordinate(latitude: 48.856613, longitude: 2.352222)
    }
}

/// Returns fixed conditions; never touches the network.
@MainActor private final class CountingWeather: WeatherForecastClient {
    private(set) var calls = 0
    var failure: WeatherAutofillError?
    func conditions(at coordinate: RoundedCoordinate, nearest start: Date) async throws -> WeatherConditions {
        calls += 1
        if let failure { throw failure }
        return WeatherConditions(temperatureC: 11.6, humidityPercent: 79, forecastHour: start, coordinate: coordinate,
                                 timezoneIdentifier: "Europe/Paris")
    }
}

@MainActor final class WorkoutAutofillTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suiteName = ""

    override func setUp() async throws {
        suiteName = "WorkoutAutofillTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() async throws {
        defaults.removePersistentDomain(forName: suiteName)
    }

    private func provider(health: SampleHealthWorkoutClient? = nil,
                          location: CountingLocation, weather: CountingWeather) -> WorkoutContextProvider {
        WorkoutContextProvider(health: health ?? SampleHealthWorkoutClient(), weather: WeatherAutofillService(
            consent: WeatherLocationConsentStore(defaults: defaults), location: location, weather: weather))
    }

    func testWeatherNeedsConsentBeforeAnyLookup() async throws {
        let location = CountingLocation(), weather = CountingWeather()
        let context = provider(location: location, weather: weather)
        var draft = WorkoutDraft()
        XCTAssertFalse(context.isWeatherConsentGranted, "Off by default")
        XCTAssertFalse(context.canFillWeather, "Fill in the weather is disabled until consent")

        let refused = await context.weatherSuggestion(startsAt: draft.startsAt)
        XCTAssertNil(refused)
        XCTAssertEqual(location.calls, 0)
        XCTAssertEqual(weather.calls, 0)
        XCTAssertEqual(draft.temperature, "")

        context.setWeatherConsent(true)
        XCTAssertTrue(context.canFillWeather)
        let fetched = await context.weatherSuggestion(startsAt: draft.startsAt)
        let suggestion = try XCTUnwrap(fetched)
        draft.applyWeatherSuggestion(suggestion)
        XCTAssertEqual(draft.temperature, "11.6")
        XCTAssertEqual(draft.humidity, "79")
        XCTAssertEqual(draft.weatherProvenance, "Weather from Open-Meteo for your area")
        XCTAssertEqual(location.calls, 1)
        XCTAssertEqual(weather.calls, 1)

        // Withdrawing consent clears values that still came from Open-Meteo.
        context.setWeatherConsent(false)
        draft.clearAppliedWeather()
        XCTAssertEqual(draft.temperature, "")
        XCTAssertEqual(draft.humidity, "")
        XCTAssertNil(draft.weatherProvenance)
        XCTAssertFalse(context.canFillWeather)
    }

    func testEditedWeatherLosesProvenanceAndSurvivesWithdrawal() async throws {
        let context = provider(location: CountingLocation(), weather: CountingWeather())
        context.setWeatherConsent(true)
        var draft = WorkoutDraft()
        let fetched = await context.weatherSuggestion(startsAt: draft.startsAt); draft.applyWeatherSuggestion(try XCTUnwrap(fetched))
        draft.temperature = "14"
        XCTAssertNil(draft.weatherProvenance, "The user's own value is not labelled as Open-Meteo's")
        draft.clearAppliedWeather()
        XCTAssertEqual(draft.temperature, "14")
        XCTAssertEqual(draft.humidity, "79")
    }

    func testWeatherFailureLeavesTheFormAndExplains() async throws {
        let weather = CountingWeather()
        weather.failure = .offline
        let context = provider(location: CountingLocation(), weather: weather)
        context.setWeatherConsent(true)
        let suggestion = await context.weatherSuggestion(startsAt: .now.addingTimeInterval(3600))
        XCTAssertNil(suggestion)
        XCTAssertEqual(context.weatherState, .failed(WeatherAutofillError.offline.errorDescription!))
        for error in [WeatherAutofillError.consentRequired, .locationDenied, .locationUnavailable, .offline,
                      .outOfForecastRange, .unavailable, .invalidResponse] {
            XCTAssertTrue(error.errorDescription!.contains("Enter the weather yourself") || error.errorDescription!.contains("enter the weather yourself")
                          || error == .consentRequired, "\(error)")
        }
    }

    func testLastWorkoutFillsActivityDurationAndStartButNeverIntensity() async throws {
        let health = SampleHealthWorkoutClient()
        let context = provider(health: health, location: CountingLocation(), weather: CountingWeather())
        var draft = WorkoutDraft()
        draft.activity = "walking"; draft.intensity = "high"
        let fetched = await context.lastWorkoutSuggestion()
        let suggestion = try XCTUnwrap(fetched)
        draft.applyLastWorkout(suggestion)
        XCTAssertEqual(draft.activity, "running")
        XCTAssertEqual(draft.duration, "45")
        XCTAssertEqual(draft.intensity, "high", "Intensity is never inferred from heart rate or energy")
        XCTAssertGreaterThan(draft.startsAt, .now)
        let applied = try XCTUnwrap(draft.lastWorkout)
        XCTAssertTrue(applied.provenance.hasPrefix(WorkoutContextProvider.sampleWorkoutProvenancePrefix))
        XCTAssertEqual(applied.averageHeartRateBPM, 148)
        XCTAssertEqual(applied.activeEnergyKilocalories, 480)
        XCTAssertNotNil(applied.typicalSessions)
        // Heart rate and energy are display only: the request has no such fields.
        draft.temperature = "20"; draft.humidity = "50"
        let encoded = try JSONEncoder().encode(draft.personalRequest(samples: []))
        let request = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let exercise = try XCTUnwrap(request["exercise"] as? [String: Any])
        XCTAssertEqual(Set(request.keys), ["mode", "timezone", "exercise", "samples", "calibration_processing_consent"])
        XCTAssertEqual(Set(exercise.keys), ["event_id", "starts_at", "duration_minutes", "conditions",
                                            "comparable_conditions_confirmed", "duration_source"])
        XCTAssertEqual(Set((exercise["conditions"] as? [String: Any] ?? [:]).keys),
                       ["activity", "intensity", "temperature_c", "humidity_percent"])
        XCTAssertEqual(exercise["duration_source"] as? String, "manual")
        XCTAssertEqual(exercise["duration_minutes"] as? Double, 45)
        // Editing the suggestion removes its provenance.
        draft.duration = "50"
        XCTAssertNil(draft.lastWorkout)
    }

    func testLastWorkoutFailureChangesNothing() async throws {
        let context = provider(health: SampleHealthWorkoutClient(isAvailable: false), location: CountingLocation(), weather: CountingWeather())
        let suggestion = await context.lastWorkoutSuggestion()
        XCTAssertNil(suggestion)
        XCTAssertEqual(context.workoutState, .failed(HealthWorkoutError.unavailable.errorDescription!))
    }
}

/// Records every call; never touches the network.
private actor StubWonderService: BeverageService {
    let preview: String
    let response: String
    let error: WonderRequestError?
    private(set) var previewed = 0
    private(set) var explained: [WorkoutExplanationRequest] = []

    init(preview: String, response: String, error: WonderRequestError? = nil) {
        self.preview = preview; self.response = response; self.error = error
    }

    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }

    func wonderWorkoutPreview(_ request: WorkoutForecastRequest) async throws -> WorkoutWonderPreview {
        previewed += 1
        return try JSONDecoder().decode(WorkoutWonderPreview.self, from: Data(preview.utf8))
    }

    func explainWorkout(_ request: WorkoutExplanationRequest) async throws -> WorkoutExplanationResponse {
        explained.append(request)
        if let error { throw error }
        return try JSONDecoder().decode(WorkoutExplanationResponse.self, from: Data(response.utf8))
    }
}
