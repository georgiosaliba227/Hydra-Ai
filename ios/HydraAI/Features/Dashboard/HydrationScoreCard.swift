import SwiftUI

@MainActor private func homeScore(_ store: BeverageStore, history: CalibrationHistoryStore, now: Date) -> HydrationScoreAvailability {
    HydrationScore.availability(logs: store.logs, summary: store.summary, state: store.state,
        mutationPending: !store.canLog, isOffline: store.isOffline,
        historyReadable: history.canSave && history.errorMessage == nil, samples: history.records, now: now, timezone: .current)
}

struct HydrationScoreCard: View {
    @EnvironmentObject private var units: DisplayUnits
    @EnvironmentObject private var store: BeverageStore
    @ObservedObject var history: CalibrationHistoryStore
    static let meaning = "Logged goal alignment, consistency and measurement support — not hydration status or a drinking requirement."
    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { clock in
            let availability = homeScore(store, history: history, now: clock.date)
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Hydration score").font(.headline)
                    Spacer()
                    Text("Experimental").font(.caption.weight(.medium)).padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.12), in: Capsule())
                }
                switch availability {
                case .available(let facts):
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text("\(facts.score)").font(.system(.largeTitle, design: .rounded).bold()).monospacedDigit()
                        Text("/100").font(.title3).foregroundStyle(.secondary)
                    }
                    .accessibilityElement(children: .ignore).accessibilityLabel("Experimental hydration score")
                    .accessibilityValue("\(facts.score) out of 100").accessibilityIdentifier("hydrationScoreValue")
                    HStack(alignment: .top, spacing: 12) {
                        scorePart("Today", points: facts.components.today_points, maximum: 50)
                        scorePart("Consistency", points: facts.components.consistency_points, maximum: 30)
                        scorePart("Measurements", points: facts.components.measurement_points, maximum: 20)
                    }
                    Text("\(facts.local_date) · current chosen goal \(units.volume(facts.goal_ml))")
                        .font(.caption).foregroundStyle(.secondary)
                case .goalRequired:
                    Text("Choose your own logged-drink goal to calculate this research score.")
                        .font(.subheadline).accessibilityIdentifier("hydrationScoreGoalRequired")
                    NavigationLink("Set up my goal") { GuidedGoalSetupView(profileStore: store.goalProfiles) }
                        .accessibilityIdentifier("scoreChooseGoal")
                case .unavailable:
                    Text("Score unavailable. Confirmed logs and readable manual history must finish loading without a pending change.")
                        .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("hydrationScoreUnavailable")
                }
                Text(Self.meaning).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Text("Method: \(HydrationScore.version)").font(.caption2).foregroundStyle(.secondary)
                NavigationLink { HydrationScoreDetailsView(history: history) } label: {
                    Label("Why this score?", systemImage: "questionmark.circle")
                }
                .accessibilityIdentifier("whyHydrationScore")
                NavigationLink { WorkoutForecastView() } label: {
                    Text("Open detailed hydration analysis").font(.footnote)
                }
                .accessibilityIdentifier("scoreDetailedAnalysis")
            }
            .hydraCard()
            .accessibilityElement(children: .contain).accessibilityIdentifier("hydrationScoreCard")
            .onChange(of: HydrationScore.localDate(clock.date, timezone: .current)) { _, _ in
                Task { try? history.reload(); await store.refresh() }
            }
        }
    }
    private func scorePart(_ title: String, points: Double, maximum: Int) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text("\(Self.points(points))/\(maximum)").font(.subheadline.weight(.semibold)).monospacedDigit()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    static func points(_ value: Double) -> String { value.formatted(.number.precision(.fractionLength(0...2))) }
}

struct HydrationScoreDetailsView: View {
    @EnvironmentObject private var units: DisplayUnits
    @EnvironmentObject private var store: BeverageStore
    @ObservedObject var history: CalibrationHistoryStore
    @StateObject private var wonder = HydrationScoreWonderController()
    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { clock in
            let availability = homeScore(store, history: history, now: clock.date)
            Form {
                Section("Experimental research rubric") {
                    Text(HydrationScoreCard.meaning)
                    Text("floor(50 × T + 30 × C + 20 × M + 0.5)")
                        .font(.system(.subheadline, design: .monospaced)).accessibilityIdentifier("hydrationScoreFormula")
                    Text("T compares today's confirmed logged volume with your current chosen goal, capped at the goal. C averages the same capped comparison over the previous seven local calendar days. M counts up to six validated manual sessions.")
                    Text("These product weights are unvalidated. More measurements do not establish better accuracy or narrower uncertainty.")
                    Text("The six-session cap is a product milestone, not a physiological threshold.")
                    Text("Method: \(HydrationScore.version)").font(.caption).foregroundStyle(.secondary)
                }
                if let facts = availability.facts {
                    Section("Your dated snapshot") {
                        LabeledContent("Research score", value: "\(facts.score)/100")
                        LabeledContent("Local date", value: facts.local_date)
                        LabeledContent("Timezone", value: facts.timezone)
                        LabeledContent("Current chosen goal", value: "\(units.volume(facts.goal_ml))")
                        LabeledContent("Today's logged volume", value: "\(units.volume(facts.today_ml))")
                        LabeledContent("Today points", value: "\(HydrationScoreCard.points(facts.components.today_points))/50")
                        LabeledContent("Consistency points", value: "\(HydrationScoreCard.points(facts.components.consistency_points))/30")
                        LabeledContent("Valid manual sessions", value: "\(facts.measurement_count)")
                        LabeledContent("Measurement points", value: "\(HydrationScoreCard.points(facts.components.measurement_points))/20")
                        Text("Component points are rounded only for display; the final score uses their full precision.").font(.caption)
                    }
                    Section("Previous local dates") {
                        ForEach(facts.previous_days, id: \.local_date) { day in
                            LabeledContent(day.local_date, value: day.logged ? "\(units.volume(day.total_ml)) logged" : "No logs · actual intake unknown")
                        }
                        Text("Your current goal is the retrospective reference for every date here. Historical goal versions are unavailable. Extra volume above the goal earns no extra points.").font(.caption)
                    }
                    wonderSection(facts)
                } else if availability == .goalRequired {
                    Section { NavigationLink("Set up my goal") { GuidedGoalSetupView(profileStore: store.goalProfiles) } }
                } else {
                    Section { Text("The score is unavailable while its confirmed sources are loading, stale or need review. No zero score is substituted.") }
                }
                Section("Broader context") {
                    NavigationLink("Workouts, weather and beverage analysis") { WorkoutForecastView() }
                    Text("Those factors are reviewed in the comprehensive analysis. They receive no invented score weights.").font(.caption)
                }
            }
            .onChange(of: availability) { _, _ in wonder.invalidate() }
        }
        .navigationTitle("Why this score?")
        .onReceive(store.$logs.dropFirst()) { _ in wonder.invalidate() }
        .onReceive(store.$summary.dropFirst()) { _ in wonder.invalidate() }
        .onReceive(history.$records.dropFirst()) { _ in wonder.invalidate() }
        .onChange(of: store.configurationGeneration) { _, _ in wonder.invalidate() }
        .onDisappear { wonder.invalidate() }
    }
    private func service() -> HTTPBeverageService? { try? HTTPBeverageService(configuration: store.configuration) }
    @ViewBuilder private func wonderSection(_ facts: HydrationScoreFacts) -> some View {
        Section("Muse Wonder explanation") {
            Toggle("I consent to preparing these score aggregates on my backend", isOn: $wonder.processingConsent)
                .accessibilityIdentifier("scoreProcessingConsent")
                .onChange(of: wonder.processingConsent) { _, value in if !value { wonder.invalidate() } }
            Button("Preview score facts for Muse Wonder") {
                guard let service = service() else { return }
                Task { await wonder.prepare(facts: facts, service: service) }
            }
            .disabled(!wonder.processingConsent || wonder.state == .loading || wonder.explaining)
            .accessibilityIdentifier("previewScoreWonder")
            Text("Only the dated logged-volume aggregates, current goal, validated manual-session count and computed score are prepared. Raw measurements and HealthKit records stay on this iPhone.").font(.caption)
            if wonder.state == .loading { ProgressView("Preparing exact score facts…") }
            if case .failed(let message) = wonder.state { Text(message).font(.footnote) }
            if let preview = wonder.preview {
                HydraDisclosure(title: "Exact canonical score facts to be shared (mL)", identifier: "scoreWonderExactFacts") {
                    Text(Self.json(preview.facts)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                }
                Text("Reference token cost bound: \(HydraFormat.usd(micro: Double(preview.worst_case_micro_usd))). Provider extras and final charges may be unverified.").font(.caption)
                if !preview.live_available {
                    Text("Live score explanation is currently unavailable. Check live Wonder availability in Settings. Saved results can still replay.")
                        .font(.footnote).accessibilityIdentifier("scoreWonderUnavailable")
                }
                if wonder.isQuarantined {
                    Text("These facts were already attempted and may have been charged. They will not be sent again. A new preview can recover a saved result for free.").font(.footnote)
                }
                if wonder.canOffer {
                    Toggle("Send only these reviewed score facts to Meta's Muse Wonder", isOn: $wonder.metaConsent)
                        .accessibilityIdentifier("scoreMetaConsent")
                    Button("Explain this score") {
                        guard let service = service() else { return }; Task { await wonder.explain(service: service) }
                    }
                    .disabled(!wonder.metaConsent || wonder.explaining).accessibilityIdentifier("explainHydrationScore")
                }
            }
            if wonder.explaining { ProgressView("Asking Muse Wonder once…") }
            if let result = wonder.result {
                Text(wonder.replayed ? "Saved Muse Wonder explanation · no new request or charge" : "Muse Wonder explanation")
                    .font(.subheadline.weight(.semibold)).accessibilityIdentifier("scoreWonderResult")
                Text("Wonder selects and ranks reviewed wording; Hydra computes the figures.").font(.caption)
                Text("Snapshot: \(result.facts.local_date) · \(result.facts.timezone)").font(.caption)
                ForEach(result.insights) { insight in
                    VStack(alignment: .leading, spacing: 3) { Text(insight.title).font(.subheadline.weight(.medium)); Text(units.text(insight.text)).font(.subheadline) }
                }
                ForEach(result.limitations, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
            }
            if let message = wonder.explainError { Text(message).font(.footnote) }
        }
    }
    private static func json(_ facts: HydrationScoreFacts) -> String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return (try? encoder.encode(facts)).map { String(decoding: $0, as: UTF8.self) } ?? "Facts unavailable; do not send."
    }
}
