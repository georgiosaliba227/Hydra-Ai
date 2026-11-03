import SwiftUI
import UniformTypeIdentifiers

/// Saving is a separate explicit choice from using measurements for one backend estimate.
struct CalibrationHistorySection: View {
    @ObservedObject var history: CalibrationHistoryStore
    let session: [WorkoutForecastRequest.Sample]
    let use: ([WorkoutForecastRequest.Sample]) -> Void
    let revisit: (WorkoutForecastRequest.Sample) -> Void
    let deleted: (Set<UUID>?) -> Void
    @State private var saveConsent = false
    @State private var message: String?
    @State private var export: ExportDocument?
    @State private var confirmingDelete = false

    var body: some View {
        Section {
            LabeledContent("Saved on this iPhone", value: history.records.count.formatted())
                .accessibilityIdentifier("savedCalibrationCount")
                .accessibilityValue(history.records.count.formatted())
            Toggle("Save these manual measurements on this iPhone", isOn: $saveConsent)
                .accessibilityIdentifier("saveCalibrationConsent")
            Button("Save session measurements") {
                perform {
                    try history.save(session, consent: saveConsent)
                    saveConsent = false
                    message = "Manual measurements saved on this iPhone. Backend and Meta consent are separate."
                }
            }
            .disabled(!saveConsent || session.isEmpty || !history.canSave)
            .accessibilityIdentifier("saveCalibrationHistory")
            if let error = history.errorMessage {
                Text(error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier("calibrationStorageError")
                Button("Retry reading saved history") { perform { try history.reload() } }
            }
            if !history.records.isEmpty {
                Button("Use saved measurements in this session") { use(history.records) }
                    .accessibilityIdentifier("useSavedCalibration")
                ForEach(history.records, id: \.event_id) { sample in
                    DisclosureGroup {
                        measurementDetails(sample)
                        Button("Use this measurement") { use([sample]) }
                        Button("Revisit measurement in form") { revisit(sample) }
                        Button("Delete saved measurement", role: .destructive) {
                            perform { try history.delete(ids: [sample.event_id]); deleted([sample.event_id]); message = "Saved measurement and its session copy deleted." }
                        }
                        .accessibilityIdentifier("deleteCalibration-\(sample.event_id)")
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(WorkoutForecastView.dateText(sample.observed_at)).font(.subheadline.weight(.medium))
                            Text("\(sample.conditions.activity.capitalized) · \(sample.conditions.intensity) · \(sample.measurement.duration_minutes.formatted()) min")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .accessibilityIdentifier("savedCalibration-\(sample.event_id)")
                }
                Button("Export saved manual measurements (JSON)") {
                    perform { export = ExportDocument(data: try history.exportData()) }
                }
                .accessibilityIdentifier("exportCalibrationHistory")
            }
            Button("Delete all saved manual measurements", role: .destructive) { confirmingDelete = true }
                .accessibilityIdentifier("deleteAllCalibrationHistory")
            if let message { Text(message).font(.footnote).accessibilityIdentifier("calibrationHistoryMessage") }
        } header: { Text("Manual measurement history") }
        footer: {
            Text("Nothing is saved until you choose Save. Protected on this device and excluded from backup. History belongs to this backend connection; a different token or backend has separate history. Previous connection profiles stay private and can be erased with Delete all. Delete all clears every local connection's manual history. Exports contain sensitive manual weights, intake, urine and conditions; choose where to save them. No Apple Health records, consent or AI explanations are saved here.")
        }
        .onChange(of: session.map(\.event_id)) { _, _ in saveConsent = false; message = nil }
        .onDisappear { saveConsent = false; export = nil }
        .fileExporter(isPresented: Binding(get: { export != nil }, set: { if !$0 { export = nil } }),
                      document: export, contentType: .json, defaultFilename: "hydra-manual-measurements") { result in
            if case .failure = result { message = "Manual measurement export was not saved." }
        }
        .confirmationDialog("Delete every saved manual measurement on this iPhone?", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("Delete all saved manual measurements", role: .destructive) {
                perform { try history.deleteAll(); deleted(nil); message = "All saved manual measurements deleted from this iPhone." }
            }
        } message: { Text("This clears local history for every backend connection. Measurements loaded in this session are also removed. This cannot be undone.") }
    }

    @ViewBuilder private func measurementDetails(_ sample: WorkoutForecastRequest.Sample) -> some View {
        let m = sample.measurement, e = sample.errors, c = sample.conditions
        Text("Manual measurement · comparable dry weighing confirmed")
            .font(.caption.weight(.semibold))
        Text("Conditions reviewed at entry: \(c.temperature_c.formatted()) °C · \(c.humidity_percent.formatted())% humidity")
        Text("Weight before \(m.pre_mass_kg.formatted()) ± \(e.pre_mass_kg.formatted()) kg; after \(m.post_mass_kg.formatted()) ± \(e.post_mass_kg.formatted()) kg")
        Text("Drank \(m.consumed_ml.formatted()) ± \(e.consumed_ml.formatted()) mL; urine \(m.urine_ml.formatted()) ± \(e.urine_ml.formatted()) mL")
        Text("Measured duration \(m.duration_minutes.formatted()) ± \(e.duration_minutes.formatted()) min")
        Text("User-entered manual weighing. User-reported instrument error bounds. These are observations for calibration, not a measurement of total body hydration.")
            .font(.caption).foregroundStyle(.secondary)
    }
    private func perform(_ action: () throws -> Void) {
        do { try action() } catch { message = error.localizedDescription }
    }
}
