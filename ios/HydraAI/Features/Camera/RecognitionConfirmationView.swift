import SwiftUI
import UIKit

struct RecognitionConfirmationView: View {
    @EnvironmentObject private var units: DisplayUnits
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss
    let candidate: RecognitionCandidate
    let mode: String
    let recognitionId: UUID?
    let feedbackContext: RecognitionFeedbackContext?
    let onSaved: () -> Void
    @State private var draft: RecognitionEntryDraft
    @State private var editing: Bool
    @State private var needsSizeEntry: Bool
    @State private var consumedAt = Date()
    @State private var appliedPreferredUnits = false
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
        let initialDraft = RecognitionEntryDraft(candidate: candidate)
        _draft = State(initialValue: initialDraft)
        _editing = State(initialValue: initiallyEditing)
        _needsSizeEntry = State(initialValue: initialDraft.consumedMl == nil)
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
                    Text(draft.consumedMl.map { units.volume($0) } ?? "Volume unclear")
                        .font(editing ? .title2.bold() : .largeTitle.bold()).accessibilityIdentifier("photoVolume")
                    if let label = candidate.labelCapacityMl {
                        Text("Printed size: \(units.volume(label))")
                            .font(.subheadline.bold()).accessibilityIdentifier("photoLabelCapacity")
                    }
                    Text(draft.drankAll ? "Confirm logs the whole drink." : "Confirm logs your edited amount.")
                        .font(.subheadline).accessibilityIdentifier("consumptionAssumptionSummary")
                    if draft.consumedMl == nil && draft.drankAll {
                        Text("Enter the drink size, or retake a photo showing the size label.").font(.footnote)
                    }
                    if !editing {
                        Text(mode == "mock" ? "Demo suggestion · does not interpret this photo" : "\(RecognitionPresentation(mode: mode).modelName) suggestion · please verify")
                            .font(.caption).foregroundStyle(.secondary)
                        if candidate.personalCorrection != nil {
                            Text("Your previous correction: \(candidate.suggestedIdentity)").font(.caption).accessibilityIdentifier("personalCorrectionSuggestion")
                            Text("\(RecognitionPresentation(mode: mode).modelName) suggested: \(candidate.identity)").font(.caption)
                            if let liquid = candidate.personalLiquidText {
                                Text(units.text(liquid)).font(.caption).accessibilityIdentifier("personalLiquidCorrection")
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
            }
            if editing || needsSizeEntry { volumeEditor }
            if editing {
                Section("Consumed at") {
                    DatePicker("Time", selection: $consumedAt, in: Date(timeIntervalSince1970: 946_684_800)...Date().addingTimeInterval(60))
                        .accessibilityIdentifier("photoConsumedAt")
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
                        Text("\(RecognitionPresentation(mode: mode).modelName) confidence: \(candidate.confidence) (uncalibrated)")
                        Text(candidate.suggestedCapacity.map { "Container size: \(units.volume($0))" } ?? "Container size: unknown")
                            .accessibilityIdentifier("photoCapacity")
                        Text(units.text(candidate.liquidEstimateText)).font(.caption).foregroundStyle(.secondary)
                            .accessibilityIdentifier("photoEstimate")
                        if let label = candidate.labelCapacityMl { Text("Label size: \(units.volume(label)) (unverified).") }
                        ForEach(candidate.uncertaintyReasons, id: \.self) { Text($0).font(.footnote) }
                        if let label = candidate.visibleLabelText { Text("Unverified label text: \(label)").font(.footnote) }
                        Text("Container size, liquid present and amount consumed can differ. Nutrition comes only from a verified catalogue match; otherwise it stays unknown.").font(.footnote)
                    }
                }
                Section("Nutrition") {
                    if draft.keepsProductMatch, candidate.productId != nil {
                        if let nutrition = candidate.nutrition {
                            Text("Serving basis: \(units.volume(nutrition.basisMl))")
                            if let sodium = nutrition.sodiumMg { Text("Sodium: \(sodium.formatted()) mg per serving") }
                            if let carbs = nutrition.carbohydrateG { Text("Carbohydrate: \(carbs.formatted()) g per serving") }
                            ForEach(nutrition.provenance, id: \.self) { Text($0).font(.caption).textSelection(.enabled) }
                        }
                        Text("The server checks the confirmed US Original variant against its manufacturer-sourced catalogue. Other variants require correction. Water content remains unknown.").font(.footnote)
                    } else {
                        Text("No verified nutrition match. Volume can still be logged; water content and nutrients remain unknown.").font(.footnote)
                    }
                    Text("Changing identity or type removes the suggested product match.").font(.footnote)
                }
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
        }
        .scrollDismissesKeyboard(.interactively)
        .onAppear {
            if !appliedPreferredUnits {
                draft.setUnit(units.system == .us ? .usFlOz : .millilitres)
                appliedPreferredUnits = true
            }
        }
        .onChange(of: units.system) { _, system in
            draft.setUnit(system == .us ? .usFlOz : .millilitres)
        }
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
    private var volumeEditor: some View {
        Section(draft.drankAll ? "Drink size" : "Amount to log") {
            TextField(draft.drankAll ? "Drink size" : "Amount to log",
                      text: Binding(get: { draft.volumeText }, set: { draft.setVolume($0) }))
                .keyboardType(.decimalPad).focused($focusedField, equals: .volume).accessibilityIdentifier("photoConsumed")
            Picker("Unit", selection: Binding(get: { draft.unit }, set: { draft.setUnit($0) })) {
                ForEach(RecognitionVolumeUnit.allCases) { Text($0.rawValue).tag($0) }
            }.pickerStyle(.segmented).accessibilityIdentifier("photoVolumeUnit")
            HStack {
                ForEach([250, 355, 500], id: \.self) { ml in
                    Button(units.volume(ml)) { focusedField = nil; draft.selectPreset(ml) }
                        .buttonStyle(.bordered).accessibilityIdentifier("volumePreset-\(ml)")
                }
            }
            if editing {
                if draft.drankAll {
                    Button("Log a different amount") { focusedField = nil; draft.setDrankAll(false) }
                        .accessibilityIdentifier("logDifferentAmount")
                } else {
                    Button("Use whole drink") { focusedField = nil; draft.setDrankAll(true) }
                        .accessibilityIdentifier("useWholeDrink")
                }
                if let capacity = draft.confirmedCapacityMl {
                    Button("Use full \(units.volume(capacity)) container") { focusedField = nil; draft.useFullContainer() }
                        .accessibilityIdentifier("useFullContainer")
                }
            }
            Text("Other units round to the nearest mL.").font(.footnote)
        }
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
            try await store.add(category: draft.identity, consumedMl: amount, at: consumedAt, source: "confirmed_recognition",
                productId: draft.keepsProductMatch ? candidate.productId : nil, containerMl: draft.confirmedCapacityMl,
                recognitionId: recognitionId, recognitionFeedback: feedback, consumptionAssumption: draft.assumption, beverageType: draft.drinkType)
            onSaved(); dismiss()
        } catch {
            self.error = "\(error.localizedDescription) If this entry is pending, close this form and use Retry pending beverage on Today."
        }
    }
}
