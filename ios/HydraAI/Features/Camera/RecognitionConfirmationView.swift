import SwiftUI
import UIKit

struct RecognitionConfirmationView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss
    let candidate: RecognitionCandidate
    let mode: String
    let recognitionId: UUID?
    let feedbackContext: RecognitionFeedbackContext?
    let onSaved: () -> Void
    @State private var draft: RecognitionEntryDraft
    @State private var editing: Bool
    @State private var rememberCorrection = true
    @State private var shareTraining = false
    @State private var saving = false
    @State private var error: String?
    private enum InputField: Hashable { case identity, volume }
    @FocusState private var focusedField: InputField?

    init(candidate: RecognitionCandidate, mode: String = "mock", recognitionId: UUID? = nil, initiallyEditing: Bool = false,
         feedbackContext: RecognitionFeedbackContext? = nil, onSaved: @escaping () -> Void) {
        self.candidate = candidate; self.mode = mode; self.recognitionId = recognitionId
        self.feedbackContext = feedbackContext; self.onSaved = onSaved
        _draft = State(initialValue: RecognitionEntryDraft(candidate: candidate))
        _editing = State(initialValue: initiallyEditing)
    }
    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    if !editing {
                        if let context = feedbackContext, let image = UIImage(data: context.jpeg) {
                            Image(uiImage: image).resizable().scaledToFit()
                                .frame(maxWidth: .infinity).frame(height: 120).accessibilityLabel("Selected drink photo")
                        }
                        Text(draft.identity.isEmpty ? "Unknown drink" : draft.identity).font(.title2.bold())
                            .accessibilityIdentifier("reviewDrinkName")
                        if let brand = candidate.brand { Text(brand).foregroundStyle(.secondary) }
                        if draft.drinkType.caseInsensitiveCompare(draft.identity) != .orderedSame {
                            Text(draft.drinkType).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    Text(draft.consumedMl.map { "\($0) mL" } ?? "Volume unclear")
                        .font(editing ? .title2.bold() : .largeTitle.bold()).accessibilityIdentifier("photoVolume")
                    if let label = candidate.labelCapacityMl {
                        Text("Printed size: \(label) mL")
                            .font(.subheadline.bold()).accessibilityIdentifier("photoLabelCapacity")
                    }
                    Text(draft.assumption == "full_container" ? "Assuming a full container, all consumed." :
                         draft.drankAll ? "Assuming you drink all the liquid." : "Only the amount you drink will be logged.")
                        .font(.subheadline).accessibilityIdentifier("consumptionAssumptionSummary")
                    if draft.consumedMl == nil { Text("Edit the volume, or retake a photo showing the size label.").font(.footnote) }
                    if !editing {
                        Text(mode == "meta_live" ? "Muse suggestion · please verify" : "Demo suggestion · does not interpret this photo")
                            .font(.caption).foregroundStyle(.secondary)
                        Text(candidate.liquidEstimateText).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("photoEstimate")
                        if candidate.personalCorrection != nil {
                            Text("Your previous correction: \(candidate.suggestedIdentity)").font(.caption).accessibilityIdentifier("personalCorrectionSuggestion")
                            Text("\(mode == "meta_live" ? "Muse" : "Demo") suggested: \(candidate.identity)").font(.caption)
                            if let liquid = candidate.personalLiquidText {
                                Text(liquid).font(.caption).accessibilityIdentifier("personalLiquidCorrection")
                            }
                        }
                    }
                }
                .padding(.vertical, 8)
            }
            if editing {
                Section("Drink") {
                    TextField("Drink name", text: $draft.identity).focused($focusedField, equals: .identity)
                        .accessibilityIdentifier("photoIdentity")
                    Picker("Type", selection: Binding(get: { draft.drinkType }, set: { draft.chooseType($0) })) {
                        ForEach(RecognitionEntryDraft.drinkTypes, id: \.self) { Text($0).tag($0) }
                    }.accessibilityIdentifier("photoDrinkType")
                }
                Section("Volume") {
                    TextField("Amount", text: Binding(get: { draft.volumeText }, set: { draft.setVolume($0) }))
                        .keyboardType(.decimalPad).focused($focusedField, equals: .volume).accessibilityIdentifier("photoConsumed")
                    Picker("Unit", selection: Binding(get: { draft.unit }, set: { draft.setUnit($0) })) {
                        ForEach(RecognitionVolumeUnit.allCases) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented).accessibilityIdentifier("photoVolumeUnit")
                    HStack {
                        ForEach([250, 355, 500], id: \.self) { ml in
                            Button("\(ml) mL") { focusedField = nil; draft.selectPreset(ml) }
                                .buttonStyle(.bordered).accessibilityIdentifier("volumePreset-\(ml)")
                        }
                    }
                    Toggle("I drank all of this", isOn: Binding(get: { draft.drankAll }, set: { draft.setDrankAll($0) }))
                        .accessibilityIdentifier("assumeEntireLiquid")
                    if let capacity = draft.confirmedCapacityMl {
                        Button("Use full \(capacity) mL container") { focusedField = nil; draft.useFullContainer() }
                            .accessibilityIdentifier("useFullContainer")
                    }
                    Text("Other units round to the nearest mL. Turn off ‘all’ to enter a partial amount.").font(.footnote)
                }
                if draft.isCorrection, let context = feedbackContext, context.memoryAvailable || context.trainingAvailable {
                    Section {
                        DisclosureGroup("Correction options") {
                            if context.memoryAvailable {
                                Toggle("Remember for me", isOn: $rememberCorrection).accessibilityIdentifier("rememberPhotoCorrection")
                                Text("Matching photos can reuse corrected details; similar labels reuse name/type only.").font(.footnote)
                            }
                            if context.trainingAvailable {
                                Toggle("Contribute photo for future training", isOn: $shareTraining).accessibilityIdentifier("shareCorrectionTraining")
                                Text("Optional. Only contribute photos you own or may share. Your backend keeps the latest 20 opted-in photos and corrected details for reviewed future training; older examples are removed. Nothing automatically trains Muse or sends a dataset to Meta. Export or delete these copies in Settings.").font(.footnote)
                                if mode == "mock" { Text("Demo examples are marked synthetic.").font(.footnote) }
                            }
                        }
                    }
                }
                Section {
                    DisclosureGroup("Photo details") {
                        Text(RecognitionPresentation(mode: mode).suggestionTitle)
                        Text("\(mode == "meta_live" ? "Muse" : "Demo") confidence: \(candidate.confidence) (uncalibrated)")
                        Text(candidate.suggestedCapacity.map { "Container size: \($0) mL" } ?? "Container size: unknown")
                            .accessibilityIdentifier("photoCapacity")
                        if let label = candidate.labelCapacityMl { Text("Label reads \(label) mL (unverified).") }
                        ForEach(candidate.uncertaintyReasons, id: \.self) { Text($0).font(.footnote) }
                        if let label = candidate.visibleLabelText { Text("Unverified label text: \(label)").font(.footnote) }
                        Text("Container size, liquid present and amount consumed can differ. Nutrition comes only from a verified catalogue match; otherwise it stays unknown.").font(.footnote)
                    }
                }
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
        }
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle(editing ? "Edit drink" : "Your drink")
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: 12) {
                if !editing {
                    Button("Edit") { editing = true }.buttonStyle(.bordered).accessibilityIdentifier("editRecognitionEntry")
                }
                Button { focusedField = nil; Task { await save() } } label: {
                    Text(saving ? "Saving…" : "Confirm").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).disabled(!draft.valid || saving || !store.canLog)
                .accessibilityIdentifier("savePhotoBeverage")
            }
            .controlSize(.large).padding().background(.regularMaterial)
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer(); Button("Done") { focusedField = nil }.accessibilityIdentifier("photoKeyboardDone")
            }
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(saving) }
        }
        .interactiveDismissDisabled(saving)
    }
    @MainActor private func save() async {
        guard draft.valid, let amount = draft.consumedMl, !saving else { return }
        saving = true; error = nil
        defer { saving = false }
        do {
            var feedback: RecognitionFeedback?
            if draft.isCorrection, let context = feedbackContext {
                let remember = rememberCorrection && context.memoryAvailable
                let share = shareTraining && context.trainingAvailable
                if remember || share {
                    feedback = RecognitionFeedback(imageSha256: context.imageSha256, sourceMode: mode, originalCandidate: candidate.feedbackReference,
                        rememberForMe: remember, shareForTraining: share, correctedLiquidMl: draft.correctedLiquidMl,
                        trainingConsentVersion: share ? RecognitionFeedback.consentVersion : nil,
                        trainingPhotoBase64: share ? context.jpeg.base64EncodedString() : nil)
                }
            }
            try await store.add(category: draft.identity, consumedMl: amount, at: .now, source: "confirmed_recognition",
                productId: draft.keepsProductMatch ? candidate.productId : nil, containerMl: draft.confirmedCapacityMl,
                recognitionId: recognitionId, recognitionFeedback: feedback, consumptionAssumption: draft.assumption, beverageType: draft.drinkType)
            onSaved(); dismiss()
        } catch {
            self.error = "\(error.localizedDescription) If this entry is pending, close this form and use Retry pending beverage on Today."
        }
    }
}
