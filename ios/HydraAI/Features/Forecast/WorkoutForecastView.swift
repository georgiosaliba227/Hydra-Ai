import SwiftUI

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

struct WorkoutForecastView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WorkoutForecastController()
    @State private var draft = WorkoutDraft()
    @State private var samples: [WorkoutForecastRequest.Sample] = []
    @State private var inputError: String?
    @State private var showingCalibration = false
    @State private var requestTask: Task<Void, Never>?
    @FocusState private var focusedField: String?

    private var connected: Bool { store.isConfigured && !store.isOffline }
    private var loading: Bool { controller.state == .loading }

    var body: some View {
        Form {
            Section {
                Text("Exercise loss estimate") .font(.headline)
                Text("Separate from water consumed and daily fluid requirements. This is not a drinking target or a dehydration diagnosis.")
                    .font(.footnote)
                if !connected { Text("Connect to your local backend in Settings to use forecasting.") }
            }
            Section("Synthetic demonstration") {
                Text("Runs the trained model on a fixed simulated workout. No personal measurements or beverage logs are used.")
                    .font(.footnote)
                Button("Run synthetic demonstration") {
                    submit(.demonstration(timezone: TimeZone.current.identifier))
                }
                .disabled(!connected || loading)
                .accessibilityIdentifier("runWorkoutDemo")
            }
            if let result = controller.result { resultSection(result) }
            Section("Planned workout · manually entered") {
                Picker("Activity", selection: $draft.activity) {
                    ForEach(["running", "cycling", "walking", "strength", "other"], id: \.self) { Text($0.capitalized).tag($0) }
                }
                Picker("Intensity", selection: $draft.intensity) {
                    ForEach(["low", "moderate", "high"], id: \.self) { Text($0.capitalized).tag($0) }
                }
                DatePicker("Starts", selection: $draft.startsAt)
                numberField("Duration (minutes)", text: $draft.duration)
                numberField("Temperature (°C)", text: $draft.temperature, signed: true)
                numberField("Relative humidity (%)", text: $draft.humidity)
                Toggle("Conditions match my past measurements", isOn: $draft.comparable)
                Text("Confirm comparable activity, intensity, weather, clothing, equipment and acclimatization. Otherwise the estimate remains unavailable.")
                    .font(.footnote)
            }
            Section("Personal calibration") {
                Text("\(samples.count) manual measurements in this session")
                Text("Measurements stay in memory on this screen. When you request an estimate, they are processed in memory by your backend, without storage or transfer to Meta. HealthKit records are not used.")
                    .font(.footnote)
                Toggle("I consent to backend processing of these manual measurements", isOn: $draft.consent)
                    .accessibilityIdentifier("workoutCalibrationConsent")
                DisclosureGroup("Add a completed workout measurement", isExpanded: $showingCalibration) {
                    Text("Use only a workout matching the conditions above. Enter measured values, including explicit zero values where measured. Do not guess error bounds.")
                        .font(.footnote)
                    DatePicker("Measurement completed", selection: $draft.observedAt, in: ...Date.now)
                    numberField("Before mass (kg)", text: $draft.preMass)
                    numberField("After mass (kg)", text: $draft.postMass)
                    numberField("Consumed during workout (mL)", text: $draft.consumed)
                    numberField("Urine during workout (mL)", text: $draft.urine)
                    numberField("Measured duration (minutes)", text: $draft.measuredDuration)
                    Text("Independently established absolute error bounds") .font(.caption)
                    numberField("Each weighing error (kg)", text: $draft.massError)
                    numberField("Consumed volume error (mL)", text: $draft.intakeError)
                    numberField("Urine volume error (mL)", text: $draft.urineError)
                    numberField("Duration error (minutes)", text: $draft.durationError)
                    Toggle("Comparable dry weighing; all intake and urine recorded", isOn: $draft.protocolConfirmed)
                    Button("Add measurement to this session") { addSample() }
                        .disabled(samples.count >= 32)
                }
                if !samples.isEmpty {
                    Button("Remove all session measurements", role: .destructive) {
                        samples = []; controller.invalidate(); draft.consent = false
                    }
                }
                Button("Estimate planned workout loss") {
                    do {
                        let request = try WorkoutForecastRequest(mode: "personal", timezone: TimeZone.current.identifier,
                            exercise: draft.exercise(), samples: samples, calibration_processing_consent: draft.consent)
                        try request.validate(); submit(request)
                    } catch { inputError = "Enter complete workout values and consent before sending any calibration measurements." }
                }
                .disabled(!connected || loading || (!samples.isEmpty && !draft.consent))
                .accessibilityIdentifier("estimateWorkout")
            }
            if let inputError { Section { Text(inputError).foregroundStyle(.red) } }
            if loading { Section { ProgressView("Calculating locally on your backend…") } }
            if case .failed(let message) = controller.state { Section { Text(message).foregroundStyle(.secondary) } }
        }
        .navigationTitle("Workout forecast")
        .scrollDismissesKeyboard(.interactively)
        .toolbar { ToolbarItemGroup(placement: .keyboard) {
            Spacer(); Button("Done") { focusedField = nil }
        } }
        .onChange(of: draft) { _, _ in invalidate(); inputError = nil }
        .onChange(of: store.configurationGeneration) { _, _ in
            invalidate(); draft.consent = false; samples = []; inputError = nil
        }
        .onDisappear { invalidate(); samples = []; draft = WorkoutDraft() }
    }

    private func numberField(_ title: String, text: Binding<String>, signed: Bool = false) -> some View {
        TextField(title, text: text).keyboardType(signed ? .numbersAndPunctuation : .decimalPad)
            .focused($focusedField, equals: title)
    }

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

    private func submit(_ request: WorkoutForecastRequest) {
        inputError = nil; focusedField = nil
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        requestTask?.cancel()
        requestTask = Task { await controller.load(request, service: service) }
    }

    @ViewBuilder private func resultSection(_ result: WorkoutForecast) -> some View {
        Section(result.synthetic ? "SIMULATED · not your measurements" : "Personal estimate") {
            if let value = result.valueMl, let lower = result.lowerMl, let upper = result.upperMl {
                Text("Estimated exercise sweat loss: \(value.formatted(.number.precision(.fractionLength(0...1)))) mL")
                    .accessibilityIdentifier("workoutPrediction")
                Text("Range: \(lower.formatted(.number.precision(.fractionLength(0...1))))–\(upper.formatted(.number.precision(.fractionLength(0...1)))) mL")
                Text(result.synthetic
                    ? "Range checked only on simulated data; it does not establish accuracy for you."
                    : "Range reflects supplied measurement errors and comparable past workouts. Future loss can differ.")
                    .font(.caption)
            } else {
                Text("Insufficient data for an exercise-loss estimate.").accessibilityIdentifier("workoutInsufficientData")
            }
            Text("Data: \(result.dataSufficiency.replacingOccurrences(of: "_", with: " "))")
            Text("Personalization: \(result.personalizationStatus.replacingOccurrences(of: "_", with: " "))")
            Text("\(result.sampleCount) calibration measurements · \(result.modelVersion)") .font(.caption)
            if let history = result.longitudinalHistory {
                Text("Calibration history: \(history.comparable_samples) comparable of \(history.total_samples) supplied workouts; \(history.recent_samples) recent measurements.")
                    .accessibilityIdentifier("longitudinalHistory")
                if let first = history.first_observed_at, let last = history.last_observed_at {
                    Text("Observation window (UTC): \(first) to \(last)").font(.caption)
                }
                Text("History is held for this session only. Recent-workout adaptation is experimental; its range is not a calibrated prediction interval.")
                    .font(.footnote)
            }
            if let missing = result.missingInputs, !missing.isEmpty {
                Text("Missing: " + missing.map { $0.replacingOccurrences(of: "_", with: " ") }.joined(separator: ", "))
                    .font(.footnote).accessibilityIdentifier("workoutMissingMeasurements")
            }
            if let comparison = result.contextComparison, let interpretation = comparison.systems["B"]?.interpretation {
                DisclosureGroup("Compare A / B / C · research mock") {
                    Text("A · Existing numerical estimate")
                    Text("B · Contextual mock; no numerical prediction")
                    Text("C · Same estimate plus contextual mock")
                    Text("No Meta response or billed request was observed. Spark and Wonder are unverified future experiment candidates, not models used for this result.")
                        .font(.footnote)
                    ForEach(["factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions"], id: \.self) { category in
                        if let texts = interpretation.reviewed_text[category], !texts.isEmpty {
                            Text(category.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption.bold())
                            ForEach(Array(texts.enumerated()), id: \.offset) { _, text in Text(text).font(.footnote) }
                        }
                    }
                    Text("Provider latency, tokens and actual cost: not observed.").font(.caption)
                }
                .accessibilityIdentifier("contextComparison")
            }
            DisclosureGroup("Input factors and provenance") {
                ForEach(result.inputFactors.keys.sorted(), id: \.self) { key in
                    Text("\(key.replacingOccurrences(of: "_", with: " ")): \(result.inputFactors[key]!.display)")
                }
                ForEach(Array(result.provenance.enumerated()), id: \.offset) { _, source in Text(source).font(.caption) }
            }
            ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, limitation in
                Text(limitation.replacingOccurrences(of: "_", with: " ")).font(.footnote)
            }
            Text("Not a drinking recommendation. Daily fluid requirements remain unavailable.") .font(.footnote)
            if let explanation = result.mockExplanation {
                DisclosureGroup("Meta explanation integration · mock only") {
                    Text("No live Meta request was made. These are reviewed local explanation fixtures.").font(.caption)
                    ForEach(Array(explanation.explanations.enumerated()), id: \.offset) { _, text in Text(text).font(.footnote) }
                }
            }
        }
    }
}
