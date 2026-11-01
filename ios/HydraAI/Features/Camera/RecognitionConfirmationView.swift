import SwiftUI

struct RecognitionConfirmationView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss
    let candidate: RecognitionCandidate
    let mode: String
    let recognitionId: UUID?
    private enum InputField: Hashable { case identity, capacity, consumed, visibleLiquid }
    @FocusState private var focusedField: InputField?
    @State private var identity: String
    @State private var container: String
    @State private var consumed = ""
    @State private var editing: Bool
    @State private var rememberCorrection = true
    @State private var shareTraining = false
    @State private var correctedLiquid = ""
    @State private var saving = false
    @State private var error: String?
    @State private var consumedAt = Date()
    let onSaved: () -> Void
    let feedbackContext: RecognitionFeedbackContext?

    init(candidate: RecognitionCandidate, mode: String = "mock", recognitionId: UUID? = nil, initiallyEditing: Bool = true,
         feedbackContext: RecognitionFeedbackContext? = nil, onSaved: @escaping () -> Void) {
        self.mode = mode; self.recognitionId = recognitionId
        self.candidate = candidate; self.onSaved = onSaved
        self.feedbackContext = feedbackContext
        _editing = State(initialValue: initiallyEditing)
        _identity = State(initialValue: candidate.suggestedIdentity)
        _container = State(initialValue: candidate.suggestedCapacity.map(String.init) ?? "")
        _correctedLiquid = State(initialValue: candidate.personalCorrection?.liquidMl.map(String.init) ?? "")
    }
    private var valid: Bool {
        guard let capacity = Int(container), let amount = Int(consumed), (1...5000).contains(capacity) else { return false }
        let liquidValid = correctedLiquid.isEmpty || Int(correctedLiquid).map({ (1...capacity).contains($0) }) == true
        return (1...5000).contains(capacity) && (1...capacity).contains(amount) && liquidValid && !identity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && identity.count <= 80
    }
    private var isCorrection: Bool { identity.trimmingCharacters(in: .whitespacesAndNewlines) != candidate.identity || Int(container) != candidate.containerMl || !correctedLiquid.isEmpty }
    var body: some View {
        Form {
            Section(RecognitionPresentation(mode: mode).suggestionTitle) {
                if let brand = candidate.brand { LabeledContent("Brand", value: brand) }
                if let product = candidate.product { LabeledContent("Product", value: product) }
                Text("\(mode == "meta_live" ? "Muse" : "Demo") confidence: \(candidate.confidence) (uncalibrated)")
                Text(candidate.liquidEstimateText).accessibilityIdentifier("photoEstimate")
                Text("Container capacity is different from liquid present and the amount you drank.").font(.footnote)
                if candidate.personalCorrection != nil {
                    Text("\(mode == "meta_live" ? "Muse" : "Demo") suggested: \(candidate.identity)").font(.footnote)
                    Text("Your previous correction: \(candidate.suggestedIdentity)").font(.footnote).accessibilityIdentifier("personalCorrectionSuggestion")
                    if let liquid = candidate.personalLiquidText {
                        Text(liquid).font(.footnote).accessibilityIdentifier("personalLiquidCorrection")
                    }
                }
                ForEach(candidate.uncertaintyReasons, id: \.self) { Text($0).font(.footnote) }
                if !editing {
                    Button("No, edit entry") { editing = true }.accessibilityIdentifier("editRecognitionEntry")
                }
                LabeledContent("Beverage identity") {
                    TextField("Identity", text: $identity).focused($focusedField, equals: .identity).multilineTextAlignment(.trailing).accessibilityIdentifier("photoIdentity")
                        .disabled(!editing)
                }
                LabeledContent("Capacity (mL)") {
                    TextField("mL", text: $container).keyboardType(.numberPad).focused($focusedField, equals: .capacity).multilineTextAlignment(.trailing).accessibilityIdentifier("photoContainer")
                        .disabled(!editing)
                }
                if editing {
                    LabeledContent("Liquid in photo (mL, if known)") {
                        TextField("Optional", text: $correctedLiquid).keyboardType(.numberPad).focused($focusedField, equals: .visibleLiquid).multilineTextAlignment(.trailing).accessibilityIdentifier("correctedPhotoLiquid")
                    }
                }
            }
            Section("How much did you actually drink?") {
                LabeledContent("Consumed (mL)") {
                    TextField("mL", text: $consumed).keyboardType(.numberPad).focused($focusedField, equals: .consumed).multilineTextAlignment(.trailing).accessibilityIdentifier("photoConsumed")
                }
                DatePicker("Consumed at", selection: $consumedAt, in: ...Date.now)
                Text("Confirm logs only this amount. An image estimate never fills it automatically.").font(.footnote)
            }
            Section("Nutrition") {
                if candidate.productId != nil && identity == candidate.identity {
                    if let nutrition = candidate.nutrition {
                        Text("Serving basis: \(nutrition.basisMl.formatted()) mL")
                        if let sodium = nutrition.sodiumMg { Text("Sodium: \(sodium.formatted()) mg per serving") }
                        if let carbs = nutrition.carbohydrateG { Text("Carbohydrate: \(carbs.formatted()) g per serving") }
                        ForEach(nutrition.provenance, id: \.self) { Text($0).font(.caption).textSelection(.enabled) }
                    }
                    Text("The server will look up the confirmed US Original variant in its manufacturer-sourced catalogue. Check your package; other variants require correction. Water content remains unknown.")
                } else {
                    Text("No verified nutrition match. Volume can still be logged; water content and nutrients remain unknown.")
                }
                Text("Changing identity removes the suggested product match.").font(.footnote)
            }
            if isCorrection, let context = feedbackContext, context.memoryAvailable || context.trainingAvailable {
                Section("Learn from this correction") {
                    if context.memoryAvailable {
                        Toggle("Remember this correction for me", isOn: $rememberCorrection).accessibilityIdentifier("rememberPhotoCorrection")
                        Text("Hydra can suggest your correction next time. Similar product labels reuse identity only; size stays uncertain unless it is the same photo.").font(.footnote)
                    }
                    if context.trainingAvailable {
                        Toggle("Contribute photo and correction for future Hydra training", isOn: $shareTraining).accessibilityIdentifier("shareCorrectionTraining")
                        Text("Optional. Only contribute a photo you own or have permission to share. Your backend keeps the latest 20 opted-in photos and their corrected details for reviewed future training; older examples are removed. This does not automatically retrain Muse or send a dataset to Meta. Export or delete them through Your data in Settings.").font(.footnote)
                        if mode == "mock" { Text("Demo examples are marked synthetic.").font(.footnote) }
                    }
                }
            }
            if let text = candidate.visibleLabelText {
                DisclosureGroup("Label text read by \(mode == "meta_live" ? "Muse" : "Demo") (unverified)") { Text(text).font(.footnote) }
            }
            if let error { Text(error).foregroundStyle(.red) }
        }
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle(editing ? "Edit entry" : "Confirm beverage")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }.accessibilityIdentifier("photoKeyboardDone")
            }
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(saving) }
            ToolbarItem(placement: .confirmationAction) {
                Button(saving ? "Saving…" : "Confirm") { Task { await save() } }
                    .disabled(!valid || saving || !store.canLog).accessibilityIdentifier("savePhotoBeverage")
            }
        }
        .interactiveDismissDisabled(saving)
    }
    @MainActor private func save() async {
        guard valid, let capacity = Int(container), let amount = Int(consumed), !saving else { return }
        saving = true; error = nil
        defer { saving = false }
        do {
            var feedback: RecognitionFeedback?
            if isCorrection, let context = feedbackContext {
                let remember = rememberCorrection && context.memoryAvailable
                let share = shareTraining && context.trainingAvailable
                if remember || share {
                    feedback = RecognitionFeedback(imageSha256: context.imageSha256, sourceMode: mode, originalCandidate: candidate.feedbackReference,
                        rememberForMe: remember, shareForTraining: share, correctedLiquidMl: Int(correctedLiquid),
                        trainingConsentVersion: share ? RecognitionFeedback.consentVersion : nil,
                        trainingPhotoBase64: share ? context.jpeg.base64EncodedString() : nil)
                }
            }
            try await store.add(category: identity, consumedMl: amount, at: consumedAt, source: "confirmed_recognition",
                                productId: identity == candidate.identity ? candidate.productId : nil, containerMl: capacity, recognitionId: recognitionId,
                                recognitionFeedback: feedback)
            onSaved(); dismiss()
        } catch {
            self.error = "\(error.localizedDescription) If confirmation is pending, close this form and use Retry pending beverage on Today."
        }
    }
}
