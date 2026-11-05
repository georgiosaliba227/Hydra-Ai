import SwiftUI

/// Corrects one confirmed log. Photo-confirmed logs keep their product category.
struct EditBeverageView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss

    let log: BeverageLog
    @State private var category: String
    @State private var volumeMl: Double?
    @State private var consumedAt: Date
    @State private var isSaving = false
    @State private var errorMessage: String?

    init(log: BeverageLog) {
        self.log = log
        _category = State(initialValue: log.category)
        _volumeMl = State(initialValue: Double(log.consumedMl))
        _consumedAt = State(initialValue: log.consumedAt)
    }

    private var parsedVolumeMl: Int? {
        CanonicalQuantityInput.wholeMilliliters(volumeMl)
    }

    private var isManual: Bool { log.source == "manual" }

    var body: some View {
        Form {
            Section("Beverage") {
                if isManual {
                    TextField("Category", text: $category)
                        .accessibilityIdentifier("editCategory")
                } else {
                    LabeledContent("Product", value: log.category)
                }
                CanonicalQuantityField("Volume", value: $volumeMl, quantity: .volume,
                                       accessibilityIdentifier: "editVolume")
                DatePicker("Consumed at", selection: $consumedAt, in: ...Date.now)
            }
            Section {
                Text(isManual
                    ? "Corrections replace this entry and are marked as user-corrected."
                    : "This entry came from a confirmed photo, so its product stays fixed. Changing the amount clears its full-drink assumption. A known container still bounds the amount.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .accessibilityAddTraits(.updatesFrequently)
                }
            }
        }
        .navigationTitle("Edit beverage")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button(isSaving ? "Saving…" : "Save") {
                    Task { await save() }
                }
                .disabled(parsedVolumeMl == nil || isSaving || !store.canLog)
                .accessibilityIdentifier("saveBeverageEdit")
            }
        }
    }

    @MainActor
    private func save() async {
        guard let volumeMl = parsedVolumeMl, !isSaving else { return }
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            try await store.update(log, category: category, consumedMl: volumeMl, at: consumedAt)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
