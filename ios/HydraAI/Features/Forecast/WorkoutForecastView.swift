import SwiftUI

// Existing integration points stay disabled until their own implementations are ready.
enum WorkoutFlowHooks {
    static let lastWorkoutEnabled = false
    static let weatherEnabled = false
    static let wonderExplanationEnabled = false
}

/// Three focused steps. Calibration and simulated results never compete with the personal draft.
struct WorkoutForecastView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WorkoutForecastController()
    @State private var draft = WorkoutDraft()
    @State private var samples: [WorkoutForecastRequest.Sample] = []
    @State private var step = 1
    @State private var showingStart = false
    @State private var showingCalibration = false
    @State private var showingDemo = false
    @State private var inputError: String?
    @State private var requestTask: Task<Void, Never>?
    @FocusState private var focusedField: String?

    private var connected: Bool { store.hasInsightsConnection }
    private var loading: Bool { controller.state == .loading }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: HydraSpacing.section) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Step \(step) of 3").font(.subheadline.weight(.medium)).foregroundStyle(Color.hydraTint)
                        Text(step == 1 ? "Your workout" : step == 2 ? "Conditions" : "Review & estimate")
                            .font(.title2.bold())
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(.isHeader)
                    if !connected { InfoNote("Connect in Settings to calculate an estimate.", systemImage: "link") }
                    if step == 1 { workoutStep }
                    else if step == 2 { conditionsStep }
                    else { reviewStep }
                    if let inputError {
                        Text(inputError).font(.subheadline).foregroundStyle(.red)
                            .accessibilityIdentifier("workoutInputError")
                    }
                    if step < 3 {
                        Button { next() } label: {
                            Text(step == 1 ? "Continue" : "Review workout")
                                .frame(maxWidth: .infinity, minHeight: 30)
                        }
                            .buttonStyle(.borderedProminent).controlSize(.large)
                            .accessibilityIdentifier("workoutContinue")
                    }
                    if step == 1 {
                        Button { focusedField = nil; showingDemo = true } label: {
                            Label("Try a demo instead", systemImage: "play.circle")
                                .frame(minHeight: 44)
                        }
                        .accessibilityIdentifier("openWorkoutDemo")
                    }
                }
                .hydraScreen()
                .id("workoutTop")
            }
            .onChange(of: step) { _, _ in proxy.scrollTo("workoutTop", anchor: .top) }
            .onChange(of: controller.result?.generatedAt) { _, generatedAt in
                if generatedAt != nil { proxy.scrollTo("workoutTop", anchor: .top) }
            }
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Plan a workout")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(step > 1)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            if step > 1 {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Back", systemImage: "chevron.left") {
                        invalidate(); inputError = nil; focusedField = nil; step -= 1
                    }
                    .accessibilityIdentifier("workoutBack")
                }
            }
            ToolbarItemGroup(placement: .keyboard) {
                Spacer(); Button("Done") { focusedField = nil }.accessibilityIdentifier("workoutKeyboardDone")
            }
        }
        .onChange(of: draft) { previous, current in
            var previousInputs = previous
            previousInputs.consent = current.consent
            guard previousInputs != current else { return }
            draft.consent = false; invalidate(); inputError = nil
        }
        .onChange(of: inputError) { _, message in
            if let message { UIAccessibility.post(notification: .announcement, argument: message) }
        }
        .onChange(of: store.configurationGeneration) { _, _ in reset() }
        .onDisappear { reset() }
        .sheet(isPresented: $showingCalibration) {
            NavigationStack { WorkoutMeasurementsView(draft: $draft, samples: $samples, didChange: invalidate) }
        }
        .sheet(isPresented: $showingDemo) { NavigationStack { WorkoutDemoView() } }
    }

    private var workoutStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Personal sweat-loss estimates need measurements from past workouts.")
                .font(.subheadline).foregroundStyle(.secondary)
            VStack(spacing: 12) {
                Picker("Activity", selection: $draft.activity) {
                    ForEach(WorkoutDraft.activities, id: \.self) { Text($0.capitalized).tag($0) }
                }
                Divider()
                numberField("Duration", unit: "min", text: $draft.duration)
                Divider()
                Picker("Intensity", selection: $draft.intensity) {
                    ForEach(WorkoutDraft.intensities, id: \.self) { Text($0.capitalized).tag($0) }
                }
                Divider()
                DisclosureGroup(isExpanded: $showingStart) {
                    DatePicker("Starts", selection: $draft.startsAt)
                        .datePickerStyle(.compact)
                } label: {
                    Text("Starts \(draft.startsAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.subheadline)
                }
            }
            .pickerStyle(.menu)
            .hydraCard()
        }
    }

    private var conditionsStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(spacing: 16) {
                numberField("Temperature", unit: "°C", text: $draft.temperature, signed: true)
                Divider()
                numberField("Humidity", unit: "%", text: $draft.humidity)
            }
            .hydraCard()
            VStack(alignment: .leading, spacing: 8) {
                measurementButton
                Toggle("These conditions match my measured workouts", isOn: $draft.comparable)
                    .font(.subheadline)
                    .accessibilityIdentifier("workoutComparable")
                HydraDisclosure(title: "What needs to match?") {
                    Text("Activity, intensity, weather, clothing, equipment and acclimatization must match the workouts you measured. Otherwise no personal estimate is given.")
                }
            }
            .hydraCard()
        }
    }

    private var measurementButton: some View {
        Button {
            focusedField = nil
            do {
                _ = try draft.conditions()
                showingCalibration = true
            } catch let issue as WorkoutDraft.InputError {
                inputError = issue.message; focusedField = issue.field
            } catch { inputError = "Enter the conditions before adding a measured workout." }
        } label: {
            FeatureRow(title: "Past measurements", subtitle: samples.isEmpty ? "Needed for a personal estimate" : "\(samples.count) in this session",
                       systemImage: "scalemass")
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("workoutMeasurements")
    }

    @ViewBuilder private var reviewStep: some View {
        if let result = controller.result {
            WorkoutResultView(result: result)
            if result.valueMl == nil { measurementButton.hydraCard() }
            Button("Edit workout") { invalidate(); step = 1 }
                .frame(minHeight: 44).accessibilityIdentifier("editWorkout")
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Label("\(draft.activity.capitalized) · \(draft.intensity) intensity", systemImage: "figure.run")
                    .font(.headline)
                Text("\(draft.duration) min · \(draft.temperature) °C · \(draft.humidity)% humidity")
                    .font(.subheadline).monospacedDigit()
                Text(draft.startsAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.subheadline).foregroundStyle(.secondary)
                HStack {
                    Button("Edit workout") { step = 1 }.accessibilityIdentifier("editWorkout")
                    Spacer()
                    Button("Edit conditions") { step = 2 }
                }
                .frame(minHeight: 44)
            }
            .hydraCard()
            if samples.isEmpty || !draft.comparable {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Before you estimate").font(.headline)
                    Text(samples.isEmpty
                         ? "Add measurements from comparable past workouts to get a personal estimate."
                         : "Confirm that the conditions match your measured workouts in Conditions.")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .accessibilityIdentifier("workoutPrerequisite")
                    measurementButton
                }
                .hydraCard()
            }
            if !samples.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("\(samples.count) measurements in this session").font(.headline)
                    Toggle("I agree to backend processing of these manual measurements", isOn: $draft.consent)
                        .disabled(loading)
                        .accessibilityIdentifier("workoutCalibrationConsent")
                    Text("Processed for this estimate only. Not stored or sent to Meta; cleared when you leave this flow.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                .hydraCard()
            }
            Button { estimate() } label: {
                HStack {
                    if loading { ProgressView().tint(.white) }
                    Text("Estimate my workout")
                }
                .frame(maxWidth: .infinity, minHeight: 30)
            }
            .buttonStyle(.borderedProminent).controlSize(.large)
            .disabled(!connected || loading || samples.isEmpty || !draft.consent || !draft.comparable)
            .accessibilityIdentifier("estimateWorkout")
            if case .failed(let message) = controller.state { StatusBanner(text: message) }
            InfoNote("Estimated sweat loss, not a drinking target.")
        }
    }

    private func numberField(_ title: String, unit: String, text: Binding<String>, signed: Bool = false) -> some View {
        LabeledContent {
            HStack(spacing: 4) {
                TextField("—", text: text)
                    .multilineTextAlignment(.trailing)
                    .keyboardType(signed ? .numbersAndPunctuation : .decimalPad)
                    .focused($focusedField, equals: title)
                    .accessibilityLabel("\(title), \(unit)")
                    .frame(minWidth: 70, minHeight: 44)
                Text(unit).foregroundStyle(.secondary).accessibilityHidden(true)
            }
        } label: { Text(title).fixedSize(horizontal: false, vertical: true) }
        .id(title)
    }

    private func next() {
        focusedField = nil
        if step == 1 {
            guard let duration = WorkoutDraft.parsedNumber(draft.duration), (0.01...1440).contains(duration) else {
                inputError = "Enter a duration from 0.01 to 1,440 minutes."; focusedField = "Duration"; return
            }
            guard draft.startsAt > .now else { showingStart = true; inputError = "Choose a future start time."; return }
        } else {
            guard let temperature = WorkoutDraft.parsedNumber(draft.temperature), (-60...60).contains(temperature) else {
                inputError = "Enter a temperature from −60 to 60 °C."; focusedField = "Temperature"; return
            }
            guard let humidity = WorkoutDraft.parsedNumber(draft.humidity), (0...100).contains(humidity) else {
                inputError = "Enter humidity from 0 to 100%."; focusedField = "Humidity"; return
            }
        }
        inputError = nil; step += 1
    }

    private func estimate() {
        guard connected, !loading, !samples.isEmpty, draft.consent, draft.comparable,
              let service = try? store.insightsService() else { return }
        do {
            let request = try WorkoutForecastRequest(mode: "personal", timezone: TimeZone.current.identifier,
                exercise: draft.exercise(), samples: samples, calibration_processing_consent: draft.consent)
            try request.validate()
            // The captured request has this consent; another attempt needs a fresh opt-in.
            draft.consent = false
            requestTask?.cancel()
            requestTask = Task { await controller.load(request, service: service) }
        } catch { inputError = "Check the workout start time and conditions before estimating." }
    }

    private func invalidate() { requestTask?.cancel(); requestTask = nil; controller.invalidate() }
    private func reset() {
        invalidate(); showingCalibration = false; showingDemo = false
        samples = []; draft = WorkoutDraft(); step = 1; inputError = nil
    }
}
