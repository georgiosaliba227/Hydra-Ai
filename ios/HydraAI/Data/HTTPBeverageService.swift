import Foundation

struct DailySummary: Codable, Sendable {
    let localDate: String
    let timezone: String
    let beverageTotalMl: Double
    let estimatedWaterMl: Double?
    let forecastStatus: String
    /// Progress toward a goal the user chose; never a recommendation.
    var goal: Goal? = nil

    struct Goal: Codable, Equatable, Sendable {
        let dailyBeverageGoalMl: Int
        let basis: String
        let remainingMl: Double
        let progressRatio: Double
        enum CodingKeys: String, CodingKey {
            case basis
            case dailyBeverageGoalMl = "daily_beverage_goal_ml", remainingMl = "remaining_ml", progressRatio = "progress_ratio"
        }
        var isValid: Bool {
            basis == "user_confirmed" && (100...10_000).contains(dailyBeverageGoalMl)
                && remainingMl.isFinite && remainingMl >= 0 && progressRatio.isFinite && progressRatio >= 0
        }
    }

    enum CodingKeys: String, CodingKey {
        case localDate = "local_date", timezone, goal
        case beverageTotalMl = "beverage_total_ml", estimatedWaterMl = "estimated_water_ml"
        case forecastStatus = "forecast_status"
    }
}

struct GoalSettings: Decodable, Equatable, Sendable {
    let version: String
    let daily_beverage_goal_ml: Int?
    let goal_basis: String
}

enum ServiceError: LocalizedError {
    case configuration, credentials, invalidResponse, pending, storage, unauthorized, consent, liveRecognitionUnverified
    case server(Int)
    var errorDescription: String? {
        switch self {
        case .consent: "Explicit consent to send this image to Meta is required."
        case .configuration: "Set a valid backend URL and a development access token of at least 32 characters in Settings. HTTP is restricted to local development hosts."
        case .credentials: "The development access token could not be saved securely."
        case .invalidResponse: "The backend returned an unexpected response."
        case .pending: "A beverage is awaiting confirmation. Retry it before creating another or changing connection settings."
        case .storage: "The pending beverage could not be stored safely. No new request was sent."
        case .unauthorized: "The backend rejected the development access token. Check Settings."
        case .liveRecognitionUnverified: "Meta analysis did not return a verified result. Do not retry this Meta attempt. Ask a developer to review the ledger and any uncertain charges. You can log manually; analysis created no beverage."
        case .server(let status): "The backend could not complete this request (HTTP \(status)). Retry when it is available."
        }
    }
}

/// Refuse redirects so a backend cannot forward the local credential elsewhere.
final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

actor HTTPBeverageService: BeverageService {
    private let baseURL: URL
    private let token: String
    private let session: URLSession
    private let delegate: NoRedirectDelegate

    init(configuration: APIConfiguration, session: URLSession? = nil) throws {
        self.baseURL = try configuration.validatedURL()
        self.token = configuration.token
        self.delegate = NoRedirectDelegate()
        let options = URLSessionConfiguration.ephemeral
        options.timeoutIntervalForRequest = 15
        options.timeoutIntervalForResource = 60
        self.session = session ?? URLSession(configuration: options, delegate: delegate, delegateQueue: nil)
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { value in
            let text = try value.singleValueContainer().decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: text) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            guard let date = formatter.date(from: text) else { throw ServiceError.invalidResponse }
            return date
        }
        return decoder
    }

    private func send<T: Decodable>(_ path: String, query: [URLQueryItem] = [], request body: CreateBeverageRequest? = nil, key: UUID? = nil) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw ServiceError.configuration }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            request.httpMethod = "POST"
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(key?.uuidString, forHTTPHeaderField: "Idempotency-Key")
        }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        guard (200...299).contains(response.statusCode) else {
            if response.statusCode == 401 { throw ServiceError.unauthorized }
            throw ServiceError.server(response.statusCode)
        }
        return try Self.decoder().decode(T.self, from: data)
    }

    func analyzePhoto(_ jpeg: Data, scenario: String, mode: String = "mock", metaConsent: Bool = false) async throws -> RecognitionResult {
        guard ["mock", "meta_live"].contains(mode) else { throw ServiceError.invalidResponse }
        guard mode != "meta_live" || metaConsent else { throw ServiceError.consent }
        guard jpeg.count <= 1_048_576 else { throw ServiceError.invalidResponse }
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/recognitions"))
        request.timeoutInterval = mode == "meta_live" ? 45 : 15
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        request.httpBody = try encoder.encode(RecognitionRequest(imageBase64: jpeg.base64EncodedString(), photoConsent: true, mockScenario: scenario, mode: mode == "mock" ? nil : mode, metaPhotoConsent: mode == "mock" ? nil : metaConsent))
        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
            guard response.statusCode == 200 else { throw ServiceError.server(response.statusCode) }
            let result = try JSONDecoder().decode(RecognitionResult.self, from: data)
            try result.validate()
            guard result.mode == mode else { throw ServiceError.invalidResponse }
            return result
        } catch {
            // A timeout, HTTP error or unusable response may follow a billed
            // attempt. Never relay generic retry advice for live recognition.
            if mode == "meta_live" { throw ServiceError.liveRecognitionUnverified }
            throw error
        }
    }

    /// Sends only the history window. No calibration, wearable or photo data.
    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast {
        struct HistoryRequest: Encodable {
            let date: String
            let timezone: String
            let history_days = 7
        }
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/forecasts"))
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = try JSONEncoder().encode(HistoryRequest(date: date, timezone: timezone))
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        guard response.statusCode == 200 else { throw ServiceError.server(response.statusCode) }
        let forecast = try JSONDecoder().decode(IntakeHistoryForecast.self, from: data)
        try forecast.validate(date: date, timezone: timezone)
        return forecast
    }

    /// Manual calibration stays at the user's backend. The demo submits no measurements.
    func workoutForecast(_ payload: WorkoutForecastRequest) async throws -> WorkoutForecast {
        try payload.validate()
        var request = URLRequest(url: baseURL.appendingPathComponent("v2/workout-forecasts"))
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = try JSONEncoder().encode(payload)
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        guard response.statusCode == 200 else { throw ServiceError.server(response.statusCode) }
        let result = try JSONDecoder().decode(WorkoutForecast.self, from: data)
        try result.validate(request: payload)
        return result
    }

    /// Replays a recorded, already-settled Wonder result; the backend never dispatches for this call.
    func recordedWonderComparison(scenario: String) async throws -> HydrationContextComparison {
        var request = URLRequest(url: baseURL.appendingPathComponent("v2/hydration-context-comparison"))
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = try JSONEncoder().encode(["mode": "recorded", "scenario": scenario])
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        guard response.statusCode == 200 else { throw ServiceError.server(response.statusCode) }
        let result = try JSONDecoder().decode(HydrationContextComparison.self, from: data)
        try result.validateRecorded()
        return result
    }

    func recognitionCapabilities() async throws -> RecognitionCapabilities {
        let result: RecognitionCapabilities = try await send("v1/recognition-capabilities")
        try result.validate()
        return result
    }

    func listBeverages() async throws -> [BeverageLog] {
        struct Page: Decodable { let items: [BeverageLog]; let next_cursor: String? }
        var logs: [BeverageLog] = []; var cursor: String?; var seen = Set<String>(); var ids = Set<UUID>()
        repeat {
            var query = [URLQueryItem(name: "limit", value: "200")]
            if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
            let page: Page = try await send("v1/beverages", query: query)
            for log in page.items where ids.insert(log.id).inserted { logs.append(log) }
            cursor = page.next_cursor
            if let cursor, !seen.insert(cursor).inserted { throw ServiceError.invalidResponse }
        } while cursor != nil
        return logs
    }

    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        try request.validate()
        return try await send("v1/beverages", request: request, key: idempotencyKey)
    }

    func updateBeverage(id: UUID, _ request: UpdateBeverageRequest) async throws -> BeverageLog {
        try request.validate()
        guard request.hasChanges else { throw ServiceError.invalidResponse }
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let (data, status) = try await mutate("v1/beverages/\(id.uuidString.lowercased())", method: "PATCH",
                                              body: try encoder.encode(request))
        guard status == 200 else { throw ServiceError.server(status) }
        let log = try Self.decoder().decode(BeverageLog.self, from: data)
        guard log.id == id, log.revision == request.revision + 1 else { throw ServiceError.invalidResponse }
        return log
    }

    func deleteBeverage(id: UUID, revision: Int) async throws {
        let (_, status) = try await mutate("v1/beverages/\(id.uuidString.lowercased())", method: "DELETE", body: nil,
                                           query: [URLQueryItem(name: "revision", value: String(revision))])
        // 404 after a lost response means the earlier delete already succeeded.
        guard status == 204 || status == 404 else { throw ServiceError.server(status) }
    }

    /// The raw export, checked to be the expected format before the user saves it.
    func exportData() async throws -> Data {
        let (data, status) = try await mutate("v1/export", method: "GET", body: nil)
        guard status == 200,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["version"] as? String == "export-v1", object["beverages"] is [Any] else { throw ServiceError.invalidResponse }
        return data
    }

    func deleteAllData() async throws -> Int {
        struct Result: Decodable { let deleted_beverages: Int; let settings_cleared: Bool }
        let (data, status) = try await mutate("v1/data", method: "DELETE", body: nil,
                                              query: [URLQueryItem(name: "confirm", value: "delete-all-my-data")])
        guard status == 200 else { throw ServiceError.server(status) }
        let result = try JSONDecoder().decode(Result.self, from: data)
        guard result.settings_cleared, result.deleted_beverages >= 0 else { throw ServiceError.invalidResponse }
        return result.deleted_beverages
    }

    func goalSettings() async throws -> GoalSettings {
        let settings: GoalSettings = try await send("v1/settings")
        guard settings.version == "settings-v1", settings.goal_basis == "user_confirmed" else { throw ServiceError.invalidResponse }
        return settings
    }

    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings {
        if let milliliters { guard (100...10_000).contains(milliliters) else { throw BeverageValidationError.invalidVolume } }
        let body = try JSONSerialization.data(withJSONObject: ["daily_beverage_goal_ml": milliliters.map { $0 as Any } ?? NSNull()])
        let (data, status) = try await mutate("v1/settings", method: "PUT", body: body)
        guard status == 200 else { throw ServiceError.server(status) }
        let settings = try JSONDecoder().decode(GoalSettings.self, from: data)
        guard settings.daily_beverage_goal_ml == milliliters, settings.goal_basis == "user_confirmed" else { throw ServiceError.invalidResponse }
        return settings
    }

    func assistantQuestions() async throws -> [AssistantQuestion] {
        struct List: Decodable { let version: String; let questions: [AssistantQuestion] }
        let list: List = try await send("v1/assistant/questions")
        guard list.version == "assistant-v1" else { throw ServiceError.invalidResponse }
        return list.questions
    }

    /// The question goes only to the configured backend, which answers with local reviewed rules.
    func askAssistant(_ request: AssistantRequest) async throws -> AssistantAnswer {
        try request.validate()
        let (data, status) = try await mutate("v1/assistant", method: "POST", body: try JSONEncoder().encode(request))
        guard status == 200 else { throw ServiceError.server(status) }
        let answer = try JSONDecoder().decode(AssistantAnswer.self, from: data)
        try answer.validate(request: request)
        return answer
    }

    func wonderTrendPreview(timezone: String) async throws -> TrendPreview {
        let preview: TrendPreview = try await send("v1/wonder/trends", query: [.init(name: "timezone", value: timezone)])
        try preview.validate()
        guard preview.facts.timezone == timezone else { throw ServiceError.invalidResponse }
        return preview
    }

    /// Billable when the backend is live: sends exactly the previewed payload, once, with the user's consent.
    func explainTrends(_ request: TrendExplanationRequest) async throws -> TrendExplanationResponse {
        let (data, status) = try await mutate("v1/wonder/trends", method: "POST", body: try JSONEncoder().encode(request))
        guard status == 200 else { throw ServiceError.server(status) }
        let response = try JSONDecoder().decode(TrendExplanationResponse.self, from: data)
        try response.result.validate()
        guard response.result.payload_sha256 == request.payload_sha256 else { throw ServiceError.invalidResponse }
        return response
    }

    private func mutate(_ path: String, method: String, body: Data?, query: [URLQueryItem] = []) async throws -> (Data, Int) {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw ServiceError.configuration }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        if response.statusCode == 401 { throw ServiceError.unauthorized }
        return (data, response.statusCode)
    }

    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        try await send("v1/summary", query: [.init(name: "date", value: date), .init(name: "timezone", value: timezone)])
    }
}
