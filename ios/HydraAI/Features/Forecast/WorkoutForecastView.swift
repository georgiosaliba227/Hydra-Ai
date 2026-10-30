import SwiftUI

// MARK: - Integration hooks
// Placeholder spots in the guided flow. The Apple Health workout reader, the weather autofill and the
// "Wonder explains this workout" request are built separately (see WorkoutContextProvider,
// HealthWorkoutClient, WeatherAutofill and docs/architecture/WONDER_WORKOUT_API.md). Wire them into
// `useLastWorkout()`, `fillWeather()` and `wonderExplanationSection`, then flip these flags.
// Until then each spot stays hidden.
enum WorkoutFlowHooks {
    /// Shows "Use my last workout (Apple Health)" in step 1.
    static let lastWorkoutEnabled = false
    /// Shows "Fill in the weather" in step 2.
    static let weatherEnabled = false
    /// Shows the "Wonder explains this workout" card in step 3, below the personal estimate.
    static let wonderExplanationEnabled = false
}

private struct WorkoutDraft: Equatable {
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

    static let activities = ["running", "cycling", "walking", "strength", "other"]
    static let intensities = ["low", "moderate", "high"]

    /// Fills step 1 from a workout the user picked (e.g. their last Apple Health workout).
    mutating func applyWorkout(activity: String, intensity: String?, durationMinutes: Double) {
        if Self.activities.contains(activity) { self.activity = activity }
        if let intensity, Self.intensities.contains(intensity) { self.intensity = intensity }
        duration = durationMinutes.formatted(.number.precision(.fractionLength(0...1)).grouping(.never))
    }

    /// Fills step 2 from a weather reading the user asked for.
    mutating func applyWeather(temperatureC: Double, humidityPercent: Double) {
        temperature = temperatureC.formatted(.number.precision(.fractionLength(0...1)).grouping(.never))
        humidity = humidityPercent.formatted(.number.precision(.fractionLength(0)).grouping(.never))
    }

    private func number(_ text: String, minimum: Double = 0, maximum: Double) throws -> Double {
        guard let value = Double(text), value.isFinite, value >= minimum, value <= maximum else {
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
        .onDisappear { invalidate(); invalidateWonder(); samples = []; draft = WorkoutDraft() }
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
            // Autofill hook: wired later to the Apple Health workout reader.
            if WorkoutFlowHooks.lastWorkoutEnabled {
                Button { useLastWorkout() } label: {
                    Label("Use my last workout (Apple Health)", systemImage: "heart.text.square")
                }
                .accessibilityIdentifier("useLastWorkout")
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
            // Autofill hook: wired later to the weather service.
            if WorkoutFlowHooks.weatherEnabled {
                Button { fillWeather() } label: {
                    Label("Fill in the weather", systemImage: "cloud.sun")
                }
                .accessibilityIdentifier("fillWeather")
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
                    samples = []; controller.invalidate(); draft.consent = false
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
                    let request = try WorkoutForecastRequest(mode: "personal", timezone: TimeZone.current.identifier,
                        exercise: draft.exercise(), samples: samples, calibration_processing_consent: draft.consent)
                    try request.validate(); submit(request)
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

    /// Placeholder for "Wonder explains this workout". Follow the Trends pattern: show exactly what would be
    /// sent, a consent toggle, an explain button, then headline + insight cards + a collapsed
    /// "How this was made". Nothing is requested from here yet.
    private var wonderExplanationSection: some View {
        Section {
            Label("Muse Wonder can explain this workout against your own history.", systemImage: "sparkles")
                .font(.subheadline)
                .accessibilityIdentifier("workoutWonderPlaceholder")
        } header: {
            Text("Wonder explains this workout")
        }
    }

    // MARK: - Autofill actions (placeholders)

    private func useLastWorkout() {
        // TODO(Health agent): read the user's most recent workout on device after they tap, then call
        // draft.applyWorkout(activity:intensity:durationMinutes:). Nothing is read until then.
    }

    private func fillWeather() {
        // TODO(Weather agent): fetch current conditions after the tap, then call
        // draft.applyWeather(temperatureC:humidityPercent:).
    }

    // MARK: - Actions

    private func addSample() {
        do {
            let sample = try draft.sample()
            // Re-adding the same measurement in one session is not new evidence.
            guard !samples.contains(where: { $0.observed_at == sample.observed_at }) else {
                inputError = "A measurement at that completion time is already in this session."; return
            }
            samples.append(sample); controller.invalidate(); inputError = nil; showingCalibration = false
        } catch { inputError = "Complete all measurement and error-bound fields and confirm the weighing protocol." }
    }

    private func invalidate() {
        requestTask?.cancel(); requestTask = nil; controller.invalidate()
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
        requestTask = Task { await controller.load(request, service: service) }
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

    @ViewBuilder private func resultSections(_ result: WorkoutForecast) -> some View {
        Section {
            if let value = result.valueMl, let lower = result.lowerMl, let upper = result.upperMl {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(HydraFormat.milliliters(value)) mL")
                        .font(.system(.largeTitle, design: .rounded).bold())
                        .foregroundStyle(Color.hydraTint)
                        .accessibilityLabel("Estimated exercise sweat loss: \(HydraFormat.milliliters(value)) mL")
                        .accessibilityIdentifier("workoutPrediction")
                    Text("estimated sweat loss · likely \(HydraFormat.milliliters(lower))–\(HydraFormat.milliliters(upper)) mL")
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
                        Text("Observation window (UTC): \(first) to \(last)").font(.caption)
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
                    LabeledContent(key.replacingOccurrences(of: "_", with: " ").capitalized, value: result.inputFactors[key]!.display)
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
