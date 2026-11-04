import SwiftUI

/// The sheet owns its keyboard focus; its draft and measurements remain in the parent session.
struct WorkoutMeasurementsView: View {
    @Binding var draft: WorkoutDraft
    @Binding var samples: [WorkoutForecastRequest.Sample]
    let didChange: () -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focusedField: String?
    @State private var errorMessage: String?
    @State private var errorField: String?
    @State private var pendingFocus: String?
    @State private var active = true

    var body: some View {
        ScrollViewReader { proxy in
            Form {
                Section {
                    Text("Use a completed workout matching the conditions you entered. Record measured values, including measured zeros. Keep unknown values blank.")
                    DatePicker("Finished", selection: $draft.observedAt, in: ...Date.now)
                    numberField("Weight before", unit: "kg", text: $draft.preMass)
                    numberField("Weight after", unit: "kg", text: $draft.postMass)
                    numberField("Drank during", unit: "mL", text: $draft.consumed)
                    numberField("Urine during", unit: "mL", text: $draft.urine)
                    numberField("Measured duration", unit: "min", text: $draft.measuredDuration)
                } header: { Text("Workout measurements") }
                Section {
                    Text("Use your instrument's recorded error bounds. Don't guess.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    numberField("Each weighing ±", unit: "kg", text: $draft.massError)
                    numberField("Amount drunk ±", unit: "mL", text: $draft.intakeError)
                    numberField("Urine ±", unit: "mL", text: $draft.urineError)
                    numberField("Duration ±", unit: "min", text: $draft.durationError)
                    Toggle("Comparable dry weighing; all intake and urine recorded", isOn: $draft.protocolConfirmed)
                    if errorField == "Protocol", let errorMessage { Text(errorMessage).foregroundStyle(.red) }
                } header: { Text("Measurement accuracy") }
                Section {
                    if errorField == nil, let errorMessage { Text(errorMessage).foregroundStyle(.red) }
                    Button("Add measurement to this session") { addSample() }
                        .disabled(samples.count >= 32)
                        .accessibilityIdentifier("addWorkoutMeasurement")
                    if !samples.isEmpty {
                        Button("Remove all session measurements", role: .destructive) {
                            samples = []; draft.consent = false; didChange()
                        }
                    }
                } footer: {
                    Text("Session only. Nothing is uploaded until you review the workout and consent to processing.")
                }
            }
            .onChange(of: pendingFocus) { _, field in
                guard let field else { return }
                proxy.scrollTo(field, anchor: .center)
                Task { @MainActor in
                    await Task.yield()
                    guard active, pendingFocus == field else { return }
                    focusedField = field; pendingFocus = nil
                }
            }
        }
        .navigationTitle("Past measurements").navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Close") { focusedField = nil; dismiss() }
                    .accessibilityIdentifier("closeWorkoutMeasurements")
            }
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }.accessibilityIdentifier("workoutKeyboardDone")
            }
        }
        .onAppear { active = true }
        .onChange(of: errorMessage) { _, message in
            if let message { UIAccessibility.post(notification: .announcement, argument: message) }
        }
        .onChange(of: draft) { _, _ in errorMessage = nil; errorField = nil }
        .onDisappear { active = false; pendingFocus = nil; focusedField = nil }
    }

    private func numberField(_ title: String, unit: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            LabeledContent {
                HStack(spacing: 4) {
                    TextField("—", text: text)
                        .multilineTextAlignment(.trailing).keyboardType(.decimalPad)
                        .focused($focusedField, equals: title)
                        .accessibilityLabel("\(title), \(unit)")
                        .frame(minWidth: 70, minHeight: 44)
                    Text(unit).foregroundStyle(.secondary).accessibilityHidden(true)
                }
            } label: { Text(title).fixedSize(horizontal: false, vertical: true) }
            if errorField == title, let errorMessage {
                Text(errorMessage).font(.footnote).foregroundStyle(.red)
            }
        }
        .id(title)
    }

    private func addSample() {
        guard samples.count < 32 else { return }
        focusedField = nil
        do {
            let sample = try draft.sample()
            guard !samples.contains(where: { $0.observed_at == sample.observed_at }) else {
                errorField = nil; errorMessage = "That completion time is already in this session."; return
            }
            samples.append(sample); draft.consent = false; didChange(); dismiss()
        } catch let issue as WorkoutDraft.InputError {
            errorMessage = issue.message; errorField = issue.field
            if issue.field != "Protocol" { pendingFocus = issue.field }
        } catch {
            errorField = nil; errorMessage = "Check the workout conditions before adding measurements."
        }
    }
}
