import SwiftUI

// MARK: - Integration hooks
// Spots in the guided flow, wired to WorkoutContextProvider (Apple Health workouts read on device, weather
// from Open-Meteo only with consent) and the "Wonder explains this workout" endpoints
// (docs/architecture/WONDER_WORKOUT_API.md). Turn a flag off to hide its spot.
enum WorkoutFlowHooks {
    /// Shows "Use my last workout (Apple Health)" in step 1.
    static let lastWorkoutEnabled = true
    /// Shows the weather consent toggle and "Fill in the weather" in step 2.
    static let weatherEnabled = true
    /// Shows the "Wonder explains this workout" card in step 3, below the personal estimate.
    static let wonderExplanationEnabled = true
}

struct WorkoutDraft: Equatable {
    var activity = "running"
    var intensity = "moderate"
    var duration = ""
    var temperature = ""
    var humidity = ""
    var startsAt = Date.now.addingTimeInterval(3600)
    var comparable = false
    var consent = false
    var observedAt = Date.now.addingTimeInterval(-86400)
    var preMass = ""
    var postMass = ""
    var consumed = ""
    var urine = ""
    var measuredDuration = ""
    var massError = ""
    var intakeError = ""
    var urineError = ""
    var durationError = ""
    var protocolConfirmed = false
    /// What "Use my last workout" filled in. Its provenance shows only while those values are unchanged.
    var appliedWorkout: AppliedWorkout?
    /// What "Fill in the weather" filled in. Its provenance shows only while those values are unchanged.
    var appliedWeather: AppliedWeather?

    struct AppliedWorkout: Equatable {
        let activity: String
        let duration: String
        let provenance: String
        var activityNote: String?
        /// Display only: never sent and never used to judge hydration.
        var averageHeartRateBPM: Int?
        /// Display only: never sent.
        var activeEnergyKilocalories: Int?
        var typicalSessions: String?
    }

    struct AppliedWeather: Equatable {
        let temperature: String
        let humidity: String
        let provenance: String
    }

    static let activities = ["running", "cycling", "walking", "strength", "other"]
    static let intensities = ["low", "moderate", "high"]

    /// The Apple Health suggestion, while the form still shows its activity and duration.
    var lastWorkout: AppliedWorkout? {
        guard let appliedWorkout, appliedWorkout.activity == activity, appliedWorkout.duration == duration else { return nil }
        return appliedWorkout
    }

    /// The Open-Meteo provenance, while the form still shows its temperature and humidity.
    var weatherProvenance: String? {
        guard let appliedWeather, appliedWeather.temperature == temperature, appliedWeather.humidity == humidity else { return nil }
        return appliedWeather.provenance
    }

    /// Fills step 1 from a workout the user picked (e.g. their last Apple Health workout).
    mutating func applyWorkout(activity: String, intensity: String?, durationMinutes: Double) {
        if Self.activities.contains(activity) { self.activity = activity }
        if let intensity, Self.intensities.contains(intensity) { self.intensity = intensity }
        duration = Self.plain(durationMinutes, maximumFraction: 1)
    }

    /// Fills step 2 from a weather reading the user asked for.
    mutating func applyWeather(temperatureC: Double, humidityPercent: Double) {
        temperature = Self.plain(temperatureC, maximumFraction: 1)
        humidity = Self.plain(humidityPercent, maximumFraction: 0)
    }

    /// "Use my last workout": activity, whole-minute duration and the suggested start (the next occurrence of
    /// that workout's time of day). Intensity is never prefilled; heart rate and energy are display only.
    mutating func applyLastWorkout(_ suggestion: WorkoutContextDraft) {
        guard let suggested = suggestion.activity, let minutes = suggestion.durationMinutes,
              let provenance = suggestion.workoutProvenance else { return }
        applyWorkout(activity: suggested, intensity: nil, durationMinutes: minutes)
        if let start = suggestion.startsAt, start > .now { startsAt = start }
        appliedWorkout = AppliedWorkout(activity: activity, duration: duration, provenance: provenance,
                                        activityNote: suggestion.activityNote,
                                        averageHeartRateBPM: suggestion.averageHeartRate.map { Int($0.rounded()) },
                                        activeEnergyKilocalories: suggestion.activeEnergyKilocalories.map { Int($0.rounded()) },
                                        typicalSessions: suggestion.typicalSessions?.displayText)
    }

    /// "Fill in the weather": temperature and humidity from Open-Meteo.
    mutating func applyWeatherSuggestion(_ suggestion: WorkoutContextDraft) {
        guard let temperatureC = suggestion.temperatureC, let humidityPercent = suggestion.humidityPercent,
              let provenance = suggestion.weatherProvenance else { return }
        applyWeather(temperatureC: temperatureC, humidityPercent: humidityPercent)
        appliedWeather = AppliedWeather(temperature: temperature, humidity: humidity, provenance: provenance)
    }

    /// Weather consent withdrawn: clear values that still came from Open-Meteo; keep anything the user typed.
    mutating func clearAppliedWeather() {
        if weatherProvenance != nil { temperature = ""; humidity = "" }
        appliedWeather = nil
    }

    /// Text the form's parser reads back in any locale: no grouping, "." decimals.
    private static func plain(_ value: Double, maximumFraction: Int) -> String {
        value.formatted(.number.precision(.fractionLength(0...maximumFraction)).grouping(.never)
            .locale(Locale(identifier: "en_US_POSIX")))
    }

    private func number(_ text: String, minimum: Double = 0, maximum: Double) throws -> Double {
        let normalized = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard let value = Double(normalized), value.isFinite, value >= minimum, value <= maximum else {
            throw ServiceError.invalidResponse
        }
        return value
    }
    func conditions() throws -> WorkoutForecastRequest.Conditions {
        try .init(activity: activity, intensity: intensity,
                  temperature_c: number(temperature, minimum: -60, maximum: 60),
                  humidity_percent: number(humidity, maximum: 100))
    }
    func exercise() throws -> WorkoutForecastRequest.Exercise {
        guard startsAt > .now else { throw ServiceError.invalidResponse }
        return try .init(event_id: UUID(), starts_at: ISO8601DateFormatter().string(from: startsAt),
                         duration_minutes: number(duration, minimum: 0.01, maximum: 1440),
                         conditions: conditions(), comparable_conditions_confirmed: comparable)
    }
    func sample() throws -> WorkoutForecastRequest.Sample {
        guard protocolConfirmed, observedAt <= .now else { throw ServiceError.invalidResponse }
        let duration = try number(measuredDuration, minimum: 0.01, maximum: 1440)
        let durationBound = try number(durationError, maximum: 1440)
        guard durationBound < duration else { throw ServiceError.invalidResponse }
        let massBound = try number(massError, maximum: 500)
        return try .init(event_id: UUID(), observed_at: ISO8601DateFormatter().string(from: observedAt), conditions: conditions(),
            measurement: .init(pre_mass_kg: number(preMass, minimum: 0.01, maximum: 500),
                post_mass_kg: number(postMass, minimum: 0.01, maximum: 500), consumed_ml: number(consumed, maximum: 50000),
                urine_ml: number(urine, maximum: 50000), duration_minutes: duration),
            errors: .init(pre_mass_kg: massBound, post_mass_kg: massBound,
                consumed_ml: number(intakeError, maximum: 50000), urine_ml: number(urineError, maximum: 50000),
                duration_minutes: durationBound))
    }

    /// The one personal request this screen builds. "Estimate my workout" sends it, and the Wonder preview and
    /// explanation reuse the same value, so all three describe exactly the same workout and measurements.
    func personalRequest(samples: [WorkoutForecastRequest.Sample],
                         timezone: String = TimeZone.current.identifier) throws -> WorkoutForecastRequest {
        let request = try WorkoutForecastRequest(mode: "personal", timezone: timezone, exercise: exercise(),
                                                 samples: samples, calibration_processing_consent: consent)
        try request.validate()
        return request
    }
}

extension WorkoutContextProvider {
    /// Gate for "Fill in the weather": offered only after the user turned on location consent.
    var canFillWeather: Bool { isWeatherConsentGranted && weatherState != .loading }

    /// "Fill in the weather" for the form. Without consent nothing is looked up and nil is returned;
    /// a failure leaves its message in `weatherState` and returns nil.
    func weatherSuggestion(startsAt: Date) async -> WorkoutContextDraft? {
        guard isWeatherConsentGranted else { return nil }
        let suggestion = await fillInWeather(startsAt: startsAt)
        guard weatherState == .loaded, isWeatherConsentGranted else { return nil }
        return suggestion
    }

    /// "Use my last workout" for the form; nil on failure (the message is in `workoutState`).
    func lastWorkoutSuggestion() async -> WorkoutContextDraft? {
        let suggestion = await useLastWorkout()
        return workoutState == .loaded ? suggestion : nil
    }
}

/// Guided flow: try the demo, or 1. your workout → 2. conditions → 3. your estimate.
struct WorkoutForecastView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WorkoutForecastController()
    @StateObject private var wonder = RecordedWonderController()
    @State private var wonderTask: Task<Void, Never>?
    @State private var draft = WorkoutDraft()
    @State private var samples: [WorkoutForecastRequest.Sample] = []
    @State private var inputError: String?
    @State private var showingCalibration = false
    @State private var requestTask: Task<Void, Never>?
    /// Which button started the current request, so progress and errors show next to it.
    @State private var lastRequestWasDemo = true
    @FocusState private var focusedField: String?
    /// Apple Health workouts (on device) and, with consent, Open-Meteo weather.
    @StateObject private var context = WorkoutContextProvider.live()
    @State private var workoutTask: Task<Void, Never>?
    @State private var weatherTask: Task<Void, Never>?
    /// "Wonder explains this workout": preview at the user's backend, then one consented request.
    @StateObject private var explainer = WonderWorkoutController()
    @State private var explainerTask: Task<Void, Never>?
    @State private var wonderConsent = false

    private var connected: Bool { store.isConfigured && !store.isOffline }
    private var loading: Bool { controller.state == .loading }

    var body: some View {
        ScrollViewReader { proxy in
            Form {
                introSection
                demoSection
                if let result = controller.result, result.synthetic { resultSections(result) }
                recordedWonderSection
                workoutSection
                conditionsSection
                calibrationSection
                estimateSection
                if let result = controller.result, !result.synthetic { resultSections(result) }
                if WorkoutFlowHooks.wonderExplanationEnabled { wonderExplanationSection }
            }
            .onChange(of: controller.result?.synthetic) { _, synthetic in
                if synthetic == false { withAnimation { proxy.scrollTo("personalResult", anchor: .top) } }
            }
        }
        .navigationTitle("Plan a workout")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .toolbar { ToolbarItemGroup(placement: .keyboard) {
            Spacer(); Button("Done") { focusedField = nil }
        } }
        .onChange(of: draft) { _, _ in invalidate(); inputError = nil }
        .onChange(of: store.configurationGeneration) { _, _ in
            invalidate(); invalidateWonder(); draft.consent = false; samples = []; inputError = nil
        }
        .onDisappear {
            invalidate(); invalidateWonder(); samples = []; draft = WorkoutDraft()
            workoutTask?.cancel(); weatherTask?.cancel(); context.clear()
        }
    }

    // MARK: - Sections

    private var introSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    IconBadge(systemName: "figure.run")
                    Text("Estimate how much fluid you might lose as sweat during a planned workout.")
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
                InfoNote("Separate from what you drink. Not a drinking target or a dehydration diagnosis.")
                if !connected {
                    InfoNote("Connect to your backend in Settings to use this.", systemImage: "link")
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var demoSection: some View {
        Section {
            Button {
                lastRequestWasDemo = true
                submit(.demonstration(timezone: TimeZone.current.identifier))
            } label: {
                Label("Run the demo workout", systemImage: "play.circle.fill")
                    .font(.body.weight(.semibold))
            }
            .disabled(!connected || loading)
            .accessibilityIdentifier("runWorkoutDemo")
            if lastRequestWasDemo { requestStatus }
        } header: {
            Text("Just exploring?")
        } footer: {
            Text("Runs Hydra's model on a fixed simulated workout. None of your data is used.")
        }
    }

    private var recordedWonderSection: some View {
        Section {
            Button {
                loadWonder()
            } label: {
                Label("Show Muse Wonder's take", systemImage: "sparkles")
            }
            .disabled(!connected || wonder.state == .loading)
            .accessibilityIdentifier("loadRecordedWonder")
            if let recorded = wonder.result, let interpretation = recorded.systems["B"]?.interpretation {
                recordedWonderContent(recorded, interpretation)
            }
            if wonder.state == .loading { ProgressView() }
            if case .failed(let message) = wonder.state { Text(message).foregroundStyle(.secondary) }
        } header: {
            Text("Muse Wonder · recorded result")
        } footer: {
            Text("A real Muse Wonder 1.0 response about the demo workout, recorded earlier — loading it sends nothing to Meta. Wonder only picked which reviewed explanations apply; the numbers are Hydra's.")
        }
    }

    private var workoutSection: some View {
        Section {
            if WorkoutFlowHooks.lastWorkoutEnabled {
                Button { useLastWorkout() } label: {
                    HStack {
                        Label("Use my last workout (Apple Health)", systemImage: "heart.text.square")
                        if context.workoutState == .loading { Spacer(); ProgressView() }
                    }
                }
                .disabled(context.workoutState == .loading)
                .accessibilityIdentifier("useLastWorkout")
                if case .failed(let message) = context.workoutState {
                    Text(message).font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("lastWorkoutError")
                }
                if let applied = draft.lastWorkout { lastWorkoutDetails(applied) }
            }
            Picker("Activity", selection: $draft.activity) {
                ForEach(WorkoutDraft.activities, id: \.self) { Text($0.capitalized).tag($0) }
            }
            Picker("Intensity", selection: $draft.intensity) {
                ForEach(WorkoutDraft.intensities, id: \.self) { Text($0.capitalized).tag($0) }
            }
            DatePicker("Starts", selection: $draft.startsAt)
            numberField("Duration", unit: "min", text: $draft.duration)
        } header: {
            StepHeader(number: 1, title: "Your workout")
        }
    }

    private var conditionsSection: some View {
        Section {
            if WorkoutFlowHooks.weatherEnabled {
                Toggle(isOn: Binding(get: { context.isWeatherConsentGranted }, set: setWeatherConsent)) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Use my location to fill in the weather")
                        Text("Your approximate location (rounded to about 1 km) goes to Open-Meteo, only when you tap Fill in the weather.")
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityIdentifier("weatherConsent")
                Button { fillWeather() } label: {
                    HStack {
                        Label("Fill in the weather", systemImage: "cloud.sun")
                        if context.weatherState == .loading { Spacer(); ProgressView() }
                    }
                }
                .disabled(!context.canFillWeather)
                .accessibilityIdentifier("fillWeather")
                if case .failed(let message) = context.weatherState {
                    Text(message).font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("weatherError")
                }
                if let provenance = draft.weatherProvenance {
                    Text(provenance).font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("weatherProvenance")
                }
            }
            numberField("Temperature", unit: "°C", text: $draft.temperature, signed: true)
            numberField("Humidity", unit: "%", text: $draft.humidity)
            Toggle("Conditions match my past measurements", isOn: $draft.comparable)
        } header: {
            StepHeader(number: 2, title: "Conditions")
        } footer: {
            Text("Turn this on only if activity, intensity, weather, clothing, equipment and acclimatization match workouts you measured. Otherwise no personal estimate is given.")
        }
    }

    private var calibrationSection: some View {
        Section {
            LabeledContent("Measurements this session", value: samples.count.formatted())
            Toggle("I consent to backend processing of these manual measurements", isOn: $draft.consent)
                .accessibilityIdentifier("workoutCalibrationConsent")
            DisclosureGroup("Add a measured workout", isExpanded: $showingCalibration) {
                Text("Use only a workout that matches the conditions above. Enter measured values, including zeros where measured. Don't guess error bounds.")
                    .font(.footnote).foregroundStyle(.secondary)
                DatePicker("Finished", selection: $draft.observedAt, in: ...Date.now)
                numberField("Weight before", unit: "kg", text: $draft.preMass)
                numberField("Weight after", unit: "kg", text: $draft.postMass)
                numberField("Drank during", unit: "mL", text: $draft.consumed)
                numberField("Urine during", unit: "mL", text: $draft.urine)
                numberField("Measured duration", unit: "min", text: $draft.measuredDuration)
                Text("Measurement error bounds").font(.caption.bold()).foregroundStyle(.secondary)
                numberField("Each weighing ±", unit: "kg", text: $draft.massError)
                numberField("Amount drunk ±", unit: "mL", text: $draft.intakeError)
                numberField("Urine ±", unit: "mL", text: $draft.urineError)
                numberField("Duration ±", unit: "min", text: $draft.durationError)
                Toggle("Comparable dry weighing; all intake and urine recorded", isOn: $draft.protocolConfirmed)
                Button("Add measurement to this session") { addSample() }
                    .disabled(samples.count >= 32)
            }
            if !samples.isEmpty {
                Button("Remove all session measurements", role: .destructive) {
                    samples = []; controller.invalidate(); invalidateExplainer(); draft.consent = false
                }
            }
        } header: {
            Text("Optional · your own measurements")
        } footer: {
            Text("Measurements stay in memory on this screen. Your backend processes them only when you estimate — not stored, not sent to Meta. Apple Health records aren't used.")
        }
    }

    private var estimateSection: some View {
        Section {
            Button {
                lastRequestWasDemo = false
                do {
                    submit(try draft.personalRequest(samples: samples))
                } catch { inputError = "Fill in every workout and condition field (and consent, if you added measurements)." }
            } label: {
                Text("Estimate my workout")
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 30)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!connected || loading || (!samples.isEmpty && !draft.consent))
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
            .accessibilityIdentifier("estimateWorkout")
            if let inputError {
                Text(inputError).foregroundStyle(.red).font(.subheadline)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 8, leading: 4, bottom: 0, trailing: 4))
            }
            if !lastRequestWasDemo { requestStatus.listRowBackground(Color.clear) }
        } header: {
            StepHeader(number: 3, title: "Your estimate")
        }
    }

    @ViewBuilder private var requestStatus: some View {
        if loading { ProgressView("Calculating on your backend…") }
        if case .failed(let message) = controller.state { Text(message).foregroundStyle(.secondary) }
    }

    private func numberField(_ title: String, unit: String, text: Binding<String>, signed: Bool = false) -> some View {
        LabeledContent {
            HStack(spacing: 4) {
                TextField("0", text: text)
                    .multilineTextAlignment(.trailing)
                    .keyboardType(signed ? .numbersAndPunctuation : .decimalPad)
                    .focused($focusedField, equals: title)
                    .accessibilityLabel("\(title), \(unit)")
                Text(unit).foregroundStyle(.secondary).accessibilityHidden(true)
            }
        } label: {
            Text(title)
        }
    }

    @ViewBuilder private func lastWorkoutDetails(_ applied: WorkoutDraft.AppliedWorkout) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(applied.provenance)
                .font(.footnote.weight(.medium))
                .accessibilityIdentifier("workoutProvenance")
            Text("Filled in the activity, duration and start time. Pick the intensity yourself.")
                .font(.caption).foregroundStyle(.secondary)
            if let note = applied.activityNote {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
            if let typical = applied.typicalSessions {
                Text(typical).font(.caption).foregroundStyle(.secondary)
            }
            if let heartRate = applied.averageHeartRateBPM {
                let energy = applied.activeEnergyKilocalories.map { " · \($0) kcal active energy" } ?? ""
                Text("That workout: average heart rate \(heartRate) bpm\(energy)")
                    .font(.caption).foregroundStyle(.secondary)
                InfoNote(WorkoutContextProvider.heartRateContextNote, systemImage: "heart")
                    .accessibilityIdentifier("heartRateContextNote")
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Wonder explains this workout

    /// Follows the Trends pattern: exactly what would be sent, a consent toggle, one explain button, then the
    /// summary, insight cards and a collapsed "How this was made". The preview is computed by the user's own
    /// backend from the same request as the estimate; nothing goes to Meta without consent.
    private var wonderExplanationSection: some View {
        Section {
            Label("Muse Wonder can explain this workout against your own history.", systemImage: "sparkles")
                .font(.subheadline)
                .accessibilityIdentifier("workoutWonderPlaceholder")
            if explainer.preview == nil, explainer.state == .idle {
                Text("Estimate your workout first. You'll then see exactly what would be sent before anything goes to Meta.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if explainer.state == .loading { ProgressView("Preparing the summary on your backend…") }
            if case .failed(let message) = explainer.state {
                Text(message).font(.subheadline).foregroundStyle(.secondary)
                    .accessibilityIdentifier("workoutWonderError")
            }
            if let result = explainer.result { wonderResult(result) }
            if let preview = explainer.preview { wonderPreview(preview) }
        } header: {
            Text("Wonder explains this workout")
        } footer: {
            Text("Muse Wonder 1.0 writes the wording. Hydra computes every number and rejects advice or medical claims before you see it.")
        }
        .id("workoutWonder")
    }

    @ViewBuilder private func wonderResult(_ result: WonderWorkout) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Muse Wonder 1.0", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color.hydraTint)
            Text(result.summary)
                .font(.title3.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("workoutWonderSummary")
        }
        .padding(.vertical, 4)
        ForEach(result.insights) { insight in
            HStack(alignment: .top, spacing: 12) {
                IconBadge(systemName: Self.insightSymbol(insight.id))
                VStack(alignment: .leading, spacing: 4) {
                    Text(insight.title).font(.headline)
                    Text(insight.text)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("workoutWonderInsight-\(insight.id)")
                }
            }
            .padding(.vertical, 4)
        }
        HydraDisclosure(title: "How this was made", systemImage: "gearshape.2", identifier: "workoutWonderProvenance") {
            Text("Wording by Muse Wonder 1.0. Every number was computed and filled in by Hydra from your entries.")
            ProvenanceLine(label: "Model", value: "\(result.provenance.provider) · \(result.provenance.model)")
            if let input = result.inputTokens, let output = result.outputTokens {
                ProvenanceLine(label: "Tokens", value: "\(input) in · \(output) out")
            }
            if let cost = result.costUSD {
                ProvenanceLine(label: "Cost (usage-based)", value: "$\(cost.formatted(.number.precision(.fractionLength(4))))")
                ProvenanceLine(label: "Account", value: result.provenance.account_id)
                Text("Final billing pending.")
            }
            ProvenanceLine(label: "Attempt", value: result.provenance.attempt_id)
            ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, limitation in
                Text("• \(limitation)")
            }
        }
    }

    @ViewBuilder private func wonderPreview(_ preview: WorkoutWonderPreview) -> some View {
        let facts = preview.facts
        VStack(alignment: .leading, spacing: 8) {
            Text("What would be sent to Meta").font(.headline)
            factRow("Planned workout", Self.plannedText(facts.planned))
            factRow("Your previous sessions", Self.historyText(facts.history, activity: facts.planned.activity))
            if let typical = Self.typicalText(facts.history) { factRow("Your typical session", typical) }
            if let loss = facts.history.measured_loss_ml {
                factRow("Measured loss", "\(HydraFormat.milliliters(Double(loss))) mL (median of your weigh-ins)")
            }
            factRow("Hydra's estimate", Self.estimateText(facts.estimate))
            Text("Only these counts, medians and Hydra's rounded estimate. No dates, body weights, drinks, urine or Apple Health records.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("workoutWonderPreview")
        if !preview.live_available {
            Label("Live Muse Wonder isn't set up on this backend, so nothing can be sent from here.", systemImage: "info.circle")
                .font(.subheadline).foregroundStyle(.secondary)
                .accessibilityIdentifier("workoutWonderUnavailable")
        }
        if !preview.explainable {
            Label("Log a previous session of this activity first: add a measured workout under \"Your own measurements\", then estimate again.",
                  systemImage: "figure.run")
                .font(.subheadline).foregroundStyle(.secondary)
                .accessibilityIdentifier("workoutWonderInsufficient")
        } else if explainer.alreadyExplained {
            Label(explainer.replayed
                  ? "This workout was already explained. Showing the saved result; nothing new was sent or charged."
                  : "Explained. This exact summary won't be sent again.",
                  systemImage: "checkmark.seal")
                .font(.subheadline).foregroundStyle(.secondary)
                .accessibilityIdentifier("workoutWonderReplay")
        } else if explainer.canOffer, let account = preview.account_id {
            Toggle("Send this summary to Meta's Muse Wonder", isOn: $wonderConsent)
                .font(.body.weight(.medium))
                .accessibilityIdentifier("workoutWonderConsent")
            Button {
                explainWorkout()
            } label: {
                HStack {
                    if explainer.explaining { ProgressView().tint(.white) }
                    Label("Explain this workout", systemImage: "sparkles")
                }
                .font(.body.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 30)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!wonderConsent || !connected || explainer.explaining)
            .accessibilityIdentifier("workoutWonderExplain")
            if explainer.explaining { ProgressView("Asking Muse Wonder…") }
            if let worst = preview.worst_case_micro_usd {
                Text("One request, charged to \(account). Worst case \(HydraFormat.usd(micro: Double(worst))). Never retried automatically.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        if let message = explainer.explainError {
            Text(message).font(.subheadline).foregroundStyle(.orange)
                .accessibilityIdentifier("workoutWonderExplainError")
        }
    }

    private func factRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.footnote).foregroundStyle(.secondary)
            Text(value).font(.subheadline).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    nonisolated static func plannedText(_ planned: WorkoutFacts.Planned) -> String {
        let activity = ["strength": "strength training", "other": "exercise"][planned.activity] ?? planned.activity
        let intensity = planned.intensity.map { "\($0)-intensity " } ?? ""
        var parts = ["\(planned.duration_minutes) min of \(intensity)\(activity) in the \(planned.time_of_day)"]
        if let temperature = planned.temperature_c { parts.append("\(temperature) °C") }
        if let humidity = planned.humidity_percent { parts.append("\(humidity)% humidity") }
        parts.append(planned.conditions_confirmed ? "conditions confirmed as matching" : "conditions not confirmed as matching")
        return parts.joined(separator: " · ")
    }

    nonisolated static func historyText(_ history: WorkoutFacts.History, activity: String) -> String {
        let total = history.sessions == 1 ? "1 previous session" : "\(history.sessions) previous sessions"
        return "\(total); \(history.activity_sessions) of this activity, \(history.matching_sessions) at the same intensity, temperature and humidity, \(history.weigh_in_sessions) with a before-and-after weigh-in"
    }

    nonisolated static func typicalText(_ history: WorkoutFacts.History) -> String? {
        var parts: [String] = []
        if let minutes = history.typical_duration_minutes { parts.append("\(minutes) min") }
        if let temperature = history.typical_temperature_c { parts.append("\(temperature) °C") }
        if let humidity = history.typical_humidity_percent { parts.append("\(humidity)% humidity") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    nonisolated static func estimateText(_ estimate: WorkoutFacts.Estimate) -> String {
        guard estimate.status == "estimated", let lower = estimate.lower_ml, let upper = estimate.upper_ml else {
            return "No estimate yet"
        }
        return HydraFormat.milliliterRange(Double(lower), Double(upper)) + " of fluid loss (not a drinking target)"
    }

    private static func insightSymbol(_ id: String) -> String {
        switch id {
        case "duration_vs_typical": "timer"
        case "weather_vs_typical": "cloud.sun"
        case "comparable_history": "clock.arrow.circlepath"
        case "estimate": "drop"
        case "estimate_vs_previous": "scalemass"
        case "missing_information": "questionmark.circle"
        case "refine_estimate": "plus.circle"
        default: "sparkles"
        }
    }

    // MARK: - Autofill actions

    /// Reads the most recent workout on device only after the tap; nothing is uploaded.
    private func useLastWorkout() {
        workoutTask?.cancel()
        workoutTask = Task {
            guard let suggestion = await context.lastWorkoutSuggestion(), !Task.isCancelled else { return }
            draft.applyLastWorkout(suggestion)
        }
    }

    /// Looks up the weather only with consent, for the hour nearest the planned start.
    private func fillWeather() {
        guard context.canFillWeather else { return }
        weatherTask?.cancel()
        weatherTask = Task {
            guard let suggestion = await context.weatherSuggestion(startsAt: draft.startsAt), !Task.isCancelled else { return }
            draft.applyWeatherSuggestion(suggestion)
        }
    }

    private func setWeatherConsent(_ granted: Bool) {
        context.setWeatherConsent(granted)
        if !granted { draft.clearAppliedWeather() }
    }

    // MARK: - Actions

    private func addSample() {
        do {
            let sample = try draft.sample()
            // Re-adding the same measurement in one session is not new evidence.
            guard !samples.contains(where: { $0.observed_at == sample.observed_at }) else {
                inputError = "A measurement at that completion time is already in this session."; return
            }
            samples.append(sample); controller.invalidate(); invalidateExplainer(); inputError = nil; showingCalibration = false
        } catch { inputError = "Complete all measurement and error-bound fields and confirm the weighing protocol." }
    }

    private func invalidate() {
        requestTask?.cancel(); requestTask = nil; controller.invalidate(); invalidateExplainer()
    }

    /// The Wonder preview describes one exact request; any change to the workout or measurements drops it.
    private func invalidateExplainer() {
        explainerTask?.cancel(); explainerTask = nil; explainer.invalidate(); wonderConsent = false
    }

    /// Not billable: the user's own backend computes the summary from the request just estimated.
    private func loadExplainerPreview(_ request: WorkoutForecastRequest) {
        guard WorkoutFlowHooks.wonderExplanationEnabled, connected,
              let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        explainerTask?.cancel()
        wonderConsent = false
        explainerTask = Task { await explainer.loadPreview(request, service: service) }
    }

    /// The only billable action on this screen: one request, only after the consent toggle is on.
    private func explainWorkout() {
        guard wonderConsent, connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        wonderConsent = false
        explainerTask?.cancel()
        explainerTask = Task { await explainer.explain(consent: true, service: service) }
    }

    private func invalidateWonder() {
        wonderTask?.cancel(); wonderTask = nil; wonder.invalidate()
    }

    private func loadWonder() {
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        wonderTask?.cancel()
        wonderTask = Task { await wonder.load(service: service) }
    }

    private func submit(_ request: WorkoutForecastRequest) {
        inputError = nil; focusedField = nil
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        requestTask?.cancel()
        if request.mode == "personal" { invalidateExplainer() }
        requestTask = Task {
            await controller.load(request, service: service)
            // The Wonder preview reuses exactly the request just estimated.
            if request.mode == "personal", controller.result != nil, !Task.isCancelled { loadExplainerPreview(request) }
        }
    }

    // MARK: - Results

    private static let interpretationCategories = ["factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions"]

    @ViewBuilder private func interpretationText(_ interpretation: HydrationContextComparison.Interpretation) -> some View {
        ForEach(Self.interpretationCategories, id: \.self) { category in
            if let texts = interpretation.reviewed_text[category], !texts.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(category.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption.bold())
                        .foregroundStyle(Color.hydraTint)
                    ForEach(Array(texts.enumerated()), id: \.offset) { _, text in
                        Text(text).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    @ViewBuilder private func recordedWonderContent(_ recorded: HydrationContextComparison,
                                                    _ interpretation: HydrationContextComparison.Interpretation) -> some View {
        interpretationText(interpretation)
        DisclosureGroup("How this was made") {
            let observed = recorded.provider_observations
            if let input = observed["input_tokens"] ?? nil, let output = observed["output_tokens"] ?? nil,
               let latency = observed["latency_ms"] ?? nil, let cost = observed["usage_derived_cost_micro_usd"] ?? nil {
                Text("\(Int(input)) input · \(Int(output)) output tokens · \(Int(latency)) ms")
                    .accessibilityIdentifier("recordedWonderUsage")
                Text("Usage-derived cost \(HydraFormat.usd(micro: cost)); final billing pending.")
            }
            Text("Muse Wonder 1.0 · Georgio's experiment account · attempt \(recorded.provenance.attempt_id ?? "")")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
    }

    /// Millilitre factors as whole mL; everything else as the backend reported it.
    nonisolated static func factorText(key: String, _ factor: WorkoutForecast.Factor) -> String {
        if case .number(let value) = factor, key.hasSuffix("_ml") { return "\(HydraFormat.milliliters(value)) mL" }
        return factor.display
    }

    /// A backend UTC timestamp shown as a local date and time; the raw text if it can't be read.
    nonisolated static func dateText(_ timestamp: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: timestamp) ?? {
            formatter.formatOptions = [.withInternetDateTime]
            return formatter.date(from: timestamp)
        }()
        return date?.formatted(date: .abbreviated, time: .shortened) ?? timestamp
    }

    @ViewBuilder private func resultSections(_ result: WorkoutForecast) -> some View {
        Section {
            if let value = result.valueMl, let lower = result.lowerMl, let upper = result.upperMl {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(HydraFormat.milliliters(value)) mL")
                        .font(.system(.largeTitle, design: .rounded).bold())
                        .foregroundStyle(Color.hydraTint)
                        .accessibilityLabel("Estimated exercise sweat loss: \(HydraFormat.milliliters(value)) mL")
                        .accessibilityIdentifier("workoutPrediction")
                    Text("estimated sweat loss · likely \(HydraFormat.milliliterRange(lower, upper))")
                        .accessibilityIdentifier("workoutPredictionRange")
                        .font(.subheadline)
                    Text(result.synthetic
                        ? "Range checked only on simulated data; it doesn't show accuracy for you."
                        : "Range reflects your measurement errors and comparable past workouts. Actual loss can differ.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            } else {
                Text("Not enough data for an estimate yet.").accessibilityIdentifier("workoutInsufficientData")
            }
            if let missing = result.missingInputs, !missing.isEmpty {
                Text("Missing: " + missing.map { $0.replacingOccurrences(of: "_", with: " ") }.joined(separator: ", "))
                    .font(.footnote).accessibilityIdentifier("workoutMissingMeasurements")
            }
            if let history = result.longitudinalHistory {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Calibration history: \(history.comparable_samples) comparable of \(history.total_samples) supplied workouts; \(history.recent_samples) recent measurements.")
                        .font(.subheadline)
                        .accessibilityIdentifier("longitudinalHistory")
                    if let first = history.first_observed_at, let last = history.last_observed_at {
                        Text("Observation window: \(Self.dateText(first)) to \(Self.dateText(last))").font(.caption)
                    }
                    Text("History is held for this session only. Recent-workout adaptation is experimental; its range is not a calibrated prediction interval.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            InfoNote("Not a drinking recommendation. Hydra doesn't set daily fluid requirements.")
            DisclosureGroup("How this was made") {
                LabeledContent("Data", value: result.dataSufficiency.replacingOccurrences(of: "_", with: " "))
                LabeledContent("Personalization", value: result.personalizationStatus.replacingOccurrences(of: "_", with: " "))
                LabeledContent("Measurements used", value: result.sampleCount.formatted())
                LabeledContent("Model", value: result.modelVersion)
                ForEach(result.inputFactors.keys.sorted(), id: \.self) { key in
                    LabeledContent(key.replacingOccurrences(of: "_", with: " ").capitalized,
                                   value: Self.factorText(key: key, result.inputFactors[key]!))
                }
                ForEach(Array(result.provenance.enumerated()), id: \.offset) { _, source in Text(source).font(.caption) }
                ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, limitation in
                    Text(limitation.replacingOccurrences(of: "_", with: " ")).font(.caption)
                }
            }
            .font(.footnote)
            if let comparison = result.contextComparison, let interpretation = comparison.systems["B"]?.interpretation {
                DisclosureGroup("Compare A / B / C · research mock") {
                    Text("A · Existing numerical estimate")
                    Text("B · Contextual mock; no numerical prediction")
                    Text("C · Same estimate plus contextual mock")
                    Text("No Meta response or billed request was observed. Hydration intelligence uses Muse Wonder 1.0; this mock cannot measure its quality.")
                        .font(.footnote).foregroundStyle(.secondary)
                    interpretationText(interpretation)
                    Text("Provider latency, tokens and actual cost: not observed.").font(.caption)
                }
                .font(.footnote)
                .accessibilityIdentifier("contextComparison")
            }
            if let explanation = result.mockExplanation {
                DisclosureGroup("Meta explanation integration · mock only") {
                    Text("No live Meta request was made. These are reviewed local explanation fixtures.").font(.caption)
                    ForEach(Array(explanation.explanations.enumerated()), id: \.offset) { _, text in Text(text).font(.footnote) }
                }
                .font(.footnote)
            }
        } header: {
            Text(result.synthetic ? "SIMULATED · not your measurements" : "Personal estimate")
        }
        .id(result.synthetic ? "demoResult" : "personalResult")
    }
}
