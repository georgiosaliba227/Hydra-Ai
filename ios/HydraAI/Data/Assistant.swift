import Foundation

struct AssistantQuestion: Decodable, Identifiable, Equatable, Sendable {
    let id: String
    let text: String
}

struct AssistantRequest: Encodable, Sendable {
    var question: String?
    var question_id: String?
    var context_scope = "none"
    var date: String?
    var timezone: String?

    /// Today's logged total is sent back only with explicit consent.
    static func make(question: String? = nil, questionId: String? = nil, includeToday: Bool,
                     now: Date = .now, zone: TimeZone = .current) -> AssistantRequest {
        var request = AssistantRequest(question: question?.trimmingCharacters(in: .whitespacesAndNewlines), question_id: questionId)
        if includeToday {
            let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = zone; formatter.dateFormat = "yyyy-MM-dd"
            request.context_scope = "today_logged_total"; request.date = formatter.string(from: now); request.timezone = zone.identifier
        }
        return request
    }

    func validate() throws {
        guard (question == nil) != (question_id == nil) else { throw ServiceError.invalidResponse }
        if let question { guard (1...300).contains(question.count) else { throw ServiceError.invalidResponse } }
    }
}

/// Reviewed answers chosen by local rules; the client rejects anything that looks generated or unsafe.
struct AssistantAnswer: Decodable, Sendable {
    struct Evidence: Decodable, Equatable, Sendable {
        let title: String
        let url: String?
        let kind: String
    }
    struct Item: Decodable, Identifiable, Equatable, Sendable {
        let topic: String
        let text: String
        let evidence: [Evidence]
        var id: String { topic }
    }
    struct IntakeContext: Decodable, Equatable, Sendable {
        let local_date: String
        let timezone: String
        let beverage_total_ml: Double
        let note: String
    }
    struct Provenance: Decodable, Equatable, Sendable {
        let mode: String
        let provider: String?
        let model: String?
        let answer_origin: String
    }
    let version: String
    let question_id: String?
    let topics: [String]
    let escalation: Bool
    let answers: [Item]
    let intake_context: IntakeContext?
    let provenance: Provenance
    let limitations: [String]

    func validate(request: AssistantRequest) throws {
        guard version == "assistant-v1", question_id == request.question_id,
              provenance == .init(mode: "local_rules", provider: nil, model: nil, answer_origin: "reviewed_text"),
              (1...4).contains(answers.count), answers.map(\.topic) == topics, Set(topics).count == topics.count,
              escalation == topics.contains("urgent"), !escalation || topics.first == "urgent",
              answers.allSatisfy({ !$0.text.isEmpty && $0.text.count <= 1_000 && !$0.evidence.isEmpty }),
              answers.flatMap(\.evidence).allSatisfy({ $0.url.map { $0.hasPrefix("https://") } ?? true }),
              (intake_context != nil) == (request.context_scope == "today_logged_total"),
              (1...8).contains(limitations.count) else { throw ServiceError.invalidResponse }
        if let intake_context {
            guard intake_context.local_date == request.date, intake_context.timezone == request.timezone,
                  intake_context.beverage_total_ml.isFinite, intake_context.beverage_total_ml >= 0 else { throw ServiceError.invalidResponse }
        }
    }
}

/// Discards late replies when the question changes, the connection changes or the screen closes.
@MainActor final class AssistantController: ObservableObject {
    @Published private(set) var answer: AssistantAnswer?
    @Published private(set) var questions: [AssistantQuestion] = []
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()

    func invalidate() {
        generation = UUID(); answer = nil; state = .idle
    }

    func loadQuestions(service: any BeverageService) async {
        guard questions.isEmpty else { return }
        if let loaded = try? await service.assistantQuestions(), loaded.count <= 20 { questions = loaded }
    }

    func ask(_ request: AssistantRequest, service: any BeverageService) async {
        invalidate()
        let current = generation
        state = .loading
        do {
            try request.validate()
            let answer = try await service.askAssistant(request)
            try answer.validate(request: request)
            guard current == generation, !Task.isCancelled else { return }
            self.answer = answer; state = .loaded
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("The assistant is unavailable. Logging still works.")
        }
    }
}
