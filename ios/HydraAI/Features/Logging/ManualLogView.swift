import SwiftUI

struct ManualLogView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss

    @State private var category = "Water"
    @State private var volumeText = ""
    @State private var consumedAt = Date()
    @State private var isSaving = false
    @State private var errorMessage: String?

    private let categories = ["Water", "Tea", "Coffee", "Milk", "Juice", "Soda", "Sports drink", "Other"]

    private var parsedVolumeMl: Int? {
        guard let value = Int(volumeText), value > 0 else { return nil }
        return value
    }

    var body: some View {
        Form {
            Section("Beverage") {
                Picker("Category", selection: $category) {
                    ForEach(categories, id: \.self) { option in
                        Text(option).tag(option)
                    }
                }
                TextField("Volume in mL", text: $volumeText)
                    .keyboardType(.numberPad)
                    .accessibilityLabel("Consumed beverage volume in milliliters")
                DatePicker("Consumed at", selection: $consumedAt, in: ...Date.now)
            }

            Section {
                Text("Enter the amount you actually drank. Every beverage can contribute fluid; this log records volume only. Water content and nutrients remain unknown until sourced.")
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
        .navigationTitle("Log a beverage")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button(isSaving ? "Saving…" : "Save") {
                    Task { await save() }
                }
                .disabled(parsedVolumeMl == nil || isSaving)
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
            try await store.add(category: category.lowercased(), consumedMl: volumeMl, at: consumedAt)
            dismiss()
        } catch {
            errorMessage = "Could not save this beverage. Please check the details and try again."
        }
    }
}
