import SwiftUI

/// Reviewed hydration answers with evidence. Questions go only to the configured backend.
struct AssistantView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = AssistantController()
    @State private var question = ""
    @State private var includeToday = false
    @State private var recordedWonder = false
    @State private var showingAllQuestions = false
    @State private var task: Task<Void, Never>?
    @FocusState private var questionFocused: Bool

    private var connected: Bool { store.hasInsightsConnection }
    private var trimmed: String { question.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: HydraSpacing.section) {
                    if !connected {
                        StatusBanner(text: "Connect to your backend in Settings to ask questions.", systemImage: "link", tint: .hydraTint)
                    }
                    composer
                    // Answers sit above the suggestions so a tapped question's reply is visible without scrolling.
                    if controller.state == .loading {
                        ProgressView("Finding a reviewed answer…").frame(maxWidth: .infinity).hydraCard()
                    }
                    if case .failed(let message) = controller.state { StatusBanner(text: message) }
                    if let answer = controller.answer { answerSection(answer).id("assistantResponse") }
                    suggestions
                    InfoNote("Reviewed answers with sources. Wellness information, not medical advice.",
                             systemImage: "checkmark.shield")
                        .padding(.horizontal, 4)
                }
                .hydraScreen()
            }
            .onChange(of: controller.state) { _, state in
                if state == .loaded, controller.answer != nil { proxy.scrollTo("assistantResponse", anchor: .top) }
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Ask Hydra")
        .task(id: store.configurationGeneration) {
            guard connected, let service = try? store.insightsService() else { return }
            await controller.loadQuestions(service: service)
        }
        .onChange(of: question) { _, _ in invalidate() }
        .onChange(of: includeToday) { _, _ in invalidate() }
        .onChange(of: recordedWonder) { _, _ in
            includeToday = false; questionFocused = false; invalidate()
        }
        .onChange(of: store.configurationGeneration) { _, _ in
            includeToday = false; recordedWonder = false; invalidate()
        }
        .onDisappear { includeToday = false; questionFocused = false; invalidate() }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: HydraSpacing.item) {
            if recordedWonder {
                Label("Recorded Muse picks", systemImage: "play.rectangle")
                    .font(.headline)
                    .accessibilityIdentifier("assistantRecordedMode")
                Text("Choose a question below to replay an earlier selection. Nothing is sent to Meta; today's total is not included.")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else {
                TextField("Does coffee count?", text: $question, axis: .vertical)
                    .lineLimit(1...4)
                    .focused($questionFocused)
                    .padding(12)
                    .background(Color.hydraBackground, in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityIdentifier("assistantQuestion")
            }
            Button {
                questionFocused = false
                ask(.make(question: trimmed, includeToday: includeToday))
            } label: {
                Label("Ask", systemImage: "paperplane.fill")
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 30)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(recordedWonder || !connected || trimmed.isEmpty || trimmed.count > 300 || controller.state == .loading)
            .accessibilityIdentifier("assistantAsk")
            HydraDisclosure(title: "Answer options", systemImage: "slider.horizontal.3", identifier: "assistantOptions") {
                Toggle("Include today's logged total", isOn: $includeToday)
                    .disabled(recordedWonder)
                    .accessibilityIdentifier("assistantIncludeToday")
                if store.isOnDevice {
                    Text("Your question goes to your Hydra backend. Including today's total shares only the total from this iPhone's log.")
                }
                Toggle("Use Muse Wonder's recorded picks", isOn: $recordedWonder)
                    .accessibilityIdentifier("assistantRecordedWonder")
                Text("Recorded picks replay reviewed answers selected earlier. No new Meta request is made.")
            }
        }
        .hydraCard()
    }

    @ViewBuilder private var suggestions: some View {
        if !controller.questions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle("Popular questions")
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(showingAllQuestions ? controller.questions[...] : controller.questions.prefix(3))) { suggestion in
                        Button {
                            questionFocused = false
                            ask(recordedWonder ? .recordedWonder(questionId: suggestion.id)
                                               : .make(questionId: suggestion.id, includeToday: includeToday))
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "questionmark.bubble").foregroundStyle(Color.hydraTint)
                                    .accessibilityHidden(true)
                                Text(suggestion.text)
                                    .foregroundStyle(.primary)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 4)
                                Image(systemName: "arrow.up.forward").font(.footnote).foregroundStyle(.tertiary)
                                    .accessibilityHidden(true)
                            }
                            .frame(minHeight: 44)
                            .padding(.vertical, 6)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(!connected || controller.state == .loading)
                        .accessibilityIdentifier("suggested-\(suggestion.id)")
                        if suggestion.id != controller.questions.last?.id { Divider().padding(.leading, 34) }
                    }
                }
                .hydraCard(padding: 12)

                if controller.questions.count > 3 {
                    Button(showingAllQuestions ? "Fewer questions" : "All questions") { showingAllQuestions.toggle() }
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("assistantAllQuestions")
                }
            }
        }
    }

    // MARK: - Answers

    @ViewBuilder private func answerSection(_ answer: AssistantAnswer) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(answer.answers) { item in
                let urgent = item.topic == "urgent"
                VStack(alignment: .leading, spacing: 8) {
                    Label(urgent ? "Seek care" : item.topic.replacingOccurrences(of: "_", with: " ").capitalized,
                          systemImage: urgent ? "cross.case.fill" : "checkmark.seal.fill")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(urgent ? Color.red : Color.hydraTint)
                        .accessibilityAddTraits(.isHeader)
                    Text(item.text)
                        .font(urgent ? Font.body.weight(.semibold) : Font.body)
                        .foregroundStyle(urgent ? .red : .primary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("assistantAnswer-\(item.topic)")
                    if !item.evidence.isEmpty {
                        HydraDisclosure(title: "Sources", systemImage: "book.closed", identifier: "assistantSources-\(item.topic)") {
                            ForEach(Array(item.evidence.enumerated()), id: \.offset) { _, source in
                                if let link = source.url.flatMap(URL.init(string:)) {
                                    Link(destination: link) {
                                        Label(source.title, systemImage: "link")
                                            .multilineTextAlignment(.leading)
                                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                                            .contentShape(Rectangle())
                                    }
                                    .font(.footnote)
                                } else {
                                    Label(source.title, systemImage: "book.closed")
                                        .font(.footnote).foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.top, 2)
                    }
                }
                .hydraCard()
                .overlay {
                    if urgent {
                        RoundedRectangle(cornerRadius: HydraSpacing.cornerRadius, style: .continuous)
                            .strokeBorder(Color.red.opacity(0.5), lineWidth: 1.5)
                    }
                }
            }
            if let context = answer.intake_context {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Your log today").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text("\(context.beverage_total_ml.formatted(.number.precision(.fractionLength(0)))) mL logged on \(context.local_date)")
                        .font(.headline)
                        .accessibilityIdentifier("assistantIntakeContext")
                    Text(context.note).font(.footnote).foregroundStyle(.secondary)
                }
                .hydraCard()
            }
            if answer.isRecordedWonder, let observed = answer.provider_observations {
                HydraDisclosure(title: "How this was made · Muse Wonder 1.0", systemImage: "gearshape.2",
                                identifier: "assistantWonderProvenance") {
                    Text("Muse Wonder 1.0 picked these reviewed answers in an earlier recorded run. The wording is Hydra's reviewed text.")
                    let tokens = [(observed["input_tokens"] ?? nil), (observed["output_tokens"] ?? nil)].compactMap { $0 }.map { Int($0) }
                    if tokens.count == 2 { ProvenanceLine(label: "Tokens", value: "\(tokens[0]) in · \(tokens[1]) out") }
                    if let cost = observed["usage_derived_cost_micro_usd"] ?? nil {
                        ProvenanceLine(label: "Cost (usage-based)", value: HydraFormat.usd(micro: cost))
                        Text("Final billing pending.")
                    }
                    ProvenanceLine(label: "Attempt", value: answer.provenance.attempt_id ?? "")
                }
                .padding(.horizontal, 4)
            }
            if !answer.limitations.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(answer.limitations.enumerated()), id: \.offset) { _, limitation in
                        Text(limitation)
                    }
                }
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
            }
        }
    }

    private func ask(_ request: AssistantRequest) {
        guard connected, let service = try? store.insightsService() else { return }
        task?.cancel()
        let connection = store.configurationGeneration
        let local = store.isOnDevice && !request.wantsRecordedWonder
        task = Task {
            guard connection == store.configurationGeneration, !Task.isCancelled else { return }
            if local {
                await controller.ask(request, service: service, deviceSummary: {
                    guard connection == store.configurationGeneration, !Task.isCancelled else { throw GoalMutationError.connectionChanged }
                    let total = try await store.deviceAssistantTotal(for: request, generation: connection)
                    guard connection == store.configurationGeneration, !Task.isCancelled else { throw GoalMutationError.connectionChanged }
                    return total
                })
            } else {
                await controller.ask(request, service: service)
            }
        }
    }

    private func invalidate() {
        task?.cancel(); task = nil; controller.invalidate()
    }
}
