import SwiftUI

/// Reviewed hydration answers with evidence. Questions go only to the configured backend.
struct AssistantView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = AssistantController()
    @State private var question = ""
    @State private var includeToday = false
    @State private var recordedWonder = false
    @State private var task: Task<Void, Never>?

    private var connected: Bool { store.isConfigured && !store.isOffline }
    private var trimmed: String { question.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        Form {
            Section {
                Text("Answers are reviewed text with sources, chosen by local rules on your backend. Hydra is a wellness tool, not medical advice.")
                    .font(.footnote)
                if !connected { Text("Connect to your local backend in Settings to ask questions.") }
            }
            Section("Ask a question") {
                TextField("For example: does coffee count?", text: $question, axis: .vertical)
                    .lineLimit(1...4)
                    .accessibilityIdentifier("assistantQuestion")
                Toggle("Include today's logged total", isOn: $includeToday)
                    .accessibilityIdentifier("assistantIncludeToday")
                Button("Ask") { ask(.make(question: trimmed, includeToday: includeToday)) }
                    .disabled(!connected || trimmed.isEmpty || trimmed.count > 300 || controller.state == .loading)
                    .accessibilityIdentifier("assistantAsk")
            }
            // Answers sit above the suggestions so a tapped question's reply is visible without scrolling.
            if controller.state == .loading { Section { ProgressView() } }
            if case .failed(let message) = controller.state { Section { Text(message).foregroundStyle(.secondary) } }
            if let answer = controller.answer { answerSections(answer) }
            if !controller.questions.isEmpty {
                Section("Suggested questions") {
                    Toggle("Use Muse Wonder's recorded selection", isOn: $recordedWonder)
                        .accessibilityIdentifier("assistantRecordedWonder")
                    if recordedWonder {
                        Text("Replays answers Muse Wonder 1.0 chose earlier from the reviewed set. Nothing is sent to Meta, and today's total is not included.")
                            .font(.footnote)
                    }
                    ForEach(controller.questions) { suggestion in
                        Button(suggestion.text) {
                            ask(recordedWonder ? .recordedWonder(questionId: suggestion.id)
                                               : .make(questionId: suggestion.id, includeToday: includeToday))
                        }
                            .disabled(!connected || controller.state == .loading)
                            .accessibilityIdentifier("suggested-\(suggestion.id)")
                    }
                }
            }
        }
        .navigationTitle("Ask Hydra")
        .task {
            guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
            await controller.loadQuestions(service: service)
        }
        .onChange(of: question) { _, _ in invalidate() }
        .onChange(of: includeToday) { _, _ in invalidate() }
        .onChange(of: recordedWonder) { _, _ in invalidate() }
        .onChange(of: store.configurationGeneration) { _, _ in invalidate() }
        .onDisappear { invalidate() }
    }

    @ViewBuilder private func answerSections(_ answer: AssistantAnswer) -> some View {
        ForEach(answer.answers) { item in
            Section {
                Text(item.text)
                    .foregroundStyle(item.topic == "urgent" ? .red : .primary)
                    .accessibilityIdentifier("assistantAnswer-\(item.topic)")
                ForEach(Array(item.evidence.enumerated()), id: \.offset) { _, source in
                    if let link = source.url.flatMap(URL.init(string:)) {
                        Link(source.title, destination: link).font(.caption)
                    } else {
                        Text(source.title).font(.caption).foregroundStyle(.secondary)
                    }
                }
            } header: {
                Text(item.topic == "urgent" ? "Seek care" : item.topic.replacingOccurrences(of: "_", with: " ").capitalized)
            }
        }
        if let context = answer.intake_context {
            Section("Your log today") {
                Text("\(context.beverage_total_ml.formatted(.number.precision(.fractionLength(0)))) mL logged on \(context.local_date)")
                    .accessibilityIdentifier("assistantIntakeContext")
                Text(context.note).font(.footnote)
            }
        }
        if answer.isRecordedWonder, let observed = answer.provider_observations {
            Section("Selected by Muse Wonder 1.0") {
                let tokens = [(observed["input_tokens"] ?? nil), (observed["output_tokens"] ?? nil)].compactMap { $0 }.map { Int($0) }
                if tokens.count == 2 { Text("\(tokens[0]) input · \(tokens[1]) output tokens").font(.caption) }
                if let cost = observed["usage_derived_cost_micro_usd"] ?? nil {
                    Text("Usage-derived cost $\((cost / 1_000_000).formatted(.number.precision(.fractionLength(4)))); final billing pending.")
                        .font(.caption)
                }
                Text("Attempt \(answer.provenance.attempt_id ?? "")").font(.caption2)
            }
            .accessibilityIdentifier("assistantWonderProvenance")
        }
        Section {
            ForEach(Array(answer.limitations.enumerated()), id: \.offset) { _, limitation in
                Text(limitation).font(.footnote)
            }
        }
    }

    private func ask(_ request: AssistantRequest) {
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        task?.cancel()
        task = Task { await controller.ask(request, service: service) }
    }

    private func invalidate() {
        task?.cancel(); task = nil; controller.invalidate()
    }
}
