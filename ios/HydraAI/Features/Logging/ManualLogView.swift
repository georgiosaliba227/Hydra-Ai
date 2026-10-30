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
    private let volumePresets = [150, 250, 330, 500]

    private var parsedVolumeMl: Int? {
        guard let value = Int(volumeText), value > 0 else { return nil }
        return value
    }

    var body: some View {
        Form {
            Section("Drink") {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8) {
                    ForEach(categories, id: \.self) { option in
                        let selected = option == category
                        Button { category = option } label: {
                            VStack(spacing: 4) {
                                Image(systemName: BeverageStyle.symbol(for: option)).accessibilityHidden(true)
                                Text(option).font(.caption.weight(.medium)).lineLimit(1).minimumScaleFactor(0.8)
                            }
                            .frame(maxWidth: .infinity, minHeight: 56)
                            .foregroundStyle(selected ? Color.white : Color.primary)
                            .background(selected ? Color.hydraTint : Color.hydraTint.opacity(0.08),
                                        in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(option)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                    }
                }
                .padding(.vertical, 4)
            }

            Section {
                HStack {
                    TextField("Amount", text: $volumeText)
                        .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }
                        .keyboardType(.numberPad)
                        .font(.title2.weight(.semibold).monospacedDigit())
                        .accessibilityLabel("Consumed beverage volume in milliliters")
                        .accessibilityIdentifier("consumedVolume")
                    Text("mL").foregroundStyle(.secondary).accessibilityHidden(true)
                }
                HStack(spacing: 8) {
                    ForEach(volumePresets, id: \.self) { preset in
                        let selected = parsedVolumeMl == preset
                        Button { volumeText = String(preset) } label: {
                            Text("\(preset)")
                                .font(.subheadline.weight(.semibold).monospacedDigit())
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .foregroundStyle(selected ? Color.white : Color.hydraTint)
                                .background(selected ? Color.hydraTint : Color.hydraTint.opacity(0.10), in: Capsule())
                                .contentShape(Capsule())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("\(preset) milliliters")
                        .accessibilityAddTraits(selected ? .isSelected : [])
                    }
                }
                DatePicker("When", selection: $consumedAt, in: ...Date.now)
            } header: {
                Text("How much")
            } footer: {
                Text("Enter what you actually drank. Every drink counts toward fluid; Hydra records volume only — water content and nutrients stay unknown.")
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .accessibilityAddTraits(.updatesFrequently)
                }
            }
        }
        .navigationTitle("Log a drink")
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
                .accessibilityIdentifier("saveBeverage")
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
            errorMessage = "\(error.localizedDescription) Close this form and use Retry pending beverage on Today if confirmation is pending."
        }
    }
}
