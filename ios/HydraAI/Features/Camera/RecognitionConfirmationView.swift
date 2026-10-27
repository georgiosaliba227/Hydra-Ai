import SwiftUI

struct RecognitionConfirmationView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss
    let candidate: RecognitionCandidate
    let mode: String
    let recognitionId: UUID?
    @FocusState private var inputFocused: Bool
    @State private var identity: String
    @State private var container: String
    @State private var consumed = ""
    @State private var confirmed = false
    @State private var saving = false
    @State private var error: String?
    @State private var consumedAt = Date()
    let onSaved: () -> Void

    init(candidate: RecognitionCandidate, mode: String = "mock", recognitionId: UUID? = nil, onSaved: @escaping () -> Void) {
        self.mode = mode; self.recognitionId = recognitionId
        self.candidate = candidate; self.onSaved = onSaved
        _identity = State(initialValue: candidate.identity)
        _container = State(initialValue: candidate.containerMl.map(String.init) ?? "")
    }
    private var valid: Bool {
        guard let capacity = Int(container), let amount = Int(consumed) else { return false }
        return (1...5000).contains(capacity) && (1...capacity).contains(amount) && !identity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && identity.count <= 80
    }
    var body: some View {
        Form {
            Section(mode == "meta_live" ? "Meta suggestion — verify every field" : "Mock suggestion — verify every field") {
                Text("Confidence: \(candidate.confidence) (uncalibrated)")
                ForEach(candidate.uncertaintyReasons, id: \.self) { Text($0).font(.footnote) }
                LabeledContent("Beverage identity") {
                    TextField("Identity", text: $identity).focused($inputFocused).multilineTextAlignment(.trailing).accessibilityIdentifier("photoIdentity")
                }
                LabeledContent("Capacity (mL)") {
                    TextField("mL", text: $container).keyboardType(.numberPad).focused($inputFocused).multilineTextAlignment(.trailing).accessibilityIdentifier("photoContainer")
                }
                LabeledContent("Consumed (mL)") {
                    TextField("mL", text: $consumed).keyboardType(.numberPad).focused($inputFocused).multilineTextAlignment(.trailing).accessibilityIdentifier("photoConsumed")
                }
                DatePicker("Consumed at", selection: $consumedAt, in: ...Date.now)
                Toggle("I confirm identity, capacity and amount consumed", isOn: $confirmed).accessibilityIdentifier("confirmPhotoDetails")
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
            if let error { Text(error).foregroundStyle(.red) }
        }
        .onChange(of: identity) { _, _ in confirmed = false }
        .onChange(of: container) { _, _ in confirmed = false }
        .onChange(of: consumed) { _, _ in confirmed = false }
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle("Confirm beverage")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { inputFocused = false }.accessibilityIdentifier("photoKeyboardDone")
            }
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(saving) }
            ToolbarItem(placement: .confirmationAction) {
                Button(saving ? "Saving…" : "Save") { Task { await save() } }
                    .disabled(!valid || !confirmed || saving || !store.canLog).accessibilityIdentifier("savePhotoBeverage")
            }
        }
        .interactiveDismissDisabled(saving)
    }
    @MainActor private func save() async {
        guard valid, confirmed, let capacity = Int(container), let amount = Int(consumed), !saving else { return }
        saving = true; error = nil
        defer { saving = false }
        do {
            try await store.add(category: identity, consumedMl: amount, at: consumedAt, source: "confirmed_recognition",
                                productId: identity == candidate.identity ? candidate.productId : nil, containerMl: capacity, recognitionId: recognitionId)
            onSaved(); dismiss()
        } catch {
            self.error = "\(error.localizedDescription) If confirmation is pending, close this form and use Retry pending beverage on Today."
        }
    }
}
