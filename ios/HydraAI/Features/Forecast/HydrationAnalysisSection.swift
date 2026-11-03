import SwiftUI

struct HydrationAnalysisSection: View {
    @EnvironmentObject private var units: DisplayUnits
    @ObservedObject var controller: HydrationAnalysisController
    var body: some View {
        Section {
            if controller.state == .loading { ProgressView("Reviewing the evidence on your backend…") }
            if case .failed(let message) = controller.state {
                Text(message).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("hydrationAnalysisError")
            }
            if let result = controller.result {
                Text(result.mode == "synthetic_demo" ? "Simulated analysis · not your measurements" : "Research analysis · your reviewed inputs")
                    .font(.subheadline.weight(.semibold))
                    .accessibilityIdentifier("hydrationAnalysisProvenance")
                Text("Hydra computed this analysis on your backend. Loading it makes no Meta request. Muse Wonder's explanation is labeled separately below.")
                    .font(.caption).foregroundStyle(.secondary)
                if let volume = result.intake.beverage_volume_ml {
                    LabeledContent("Logged beverage volume", value: units.volume(volume))
                }
                LabeledContent("Documented water content", value: result.intake.water_ml.map { units.volume($0) } ?? "Unknown")
                Text("Intake records may be incomplete. Beverage volume, water content and fluid retained by the body are different quantities.")
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(result.sections) { section in
                    DisclosureGroup {
                        Text(units.text(section.text)).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                        DisclosureGroup("Facts and provenance") {
                            ForEach(section.facts.keys.sorted(), id: \.self) { key in
                                if let fact = section.facts[key] {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(key.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption.weight(.medium))
                                        Text(Self.factText(key, fact, system: units.system)).font(.caption).foregroundStyle(.secondary)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                }
                            }
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(section.title).font(.subheadline.weight(.medium))
                            Text(Self.evidence(section.evidence_status)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .accessibilityIdentifier("hydrationAnalysis-\(section.id)")
                }
                Text("A planned workout loss is not subtracted from intake. Exercise accounting needs a completed measurement and matching time window; this screen sends planned workouts only.")
                    .font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Missing information and limits") {
                    ForEach(result.missing_inputs, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ")).font(.caption) }
                    ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, text in Text(text).font(.caption) }
                    Text("Model: \(result.numerical_forecast.model_version). Generated \(WorkoutForecastView.dateText(result.generated_at)).")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        } header: { Text("Hydration intelligence") }
        footer: { Text("Historical measurements support a conditional research estimate. More measurements do not guarantee a narrower range. No body-hydration percentage or required drinking amount is inferred.") }
    }
    private static func evidence(_ value: String) -> String {
        switch value {
        case "measured": "Measured observations"
        case "estimated": "Research estimate"
        case "insufficient_data": "Insufficient evidence"
        case "synthetic": "Simulated data"
        default: "Context only"
        }
    }
    static func factText(_ key: String, _ value: WorkoutForecast.Factor, system: DisplayUnitSystem = .metric) -> String {
        guard case .number(let number) = value else {
            if case .object(let values) = value { return values.keys.sorted().map { "\($0.replacingOccurrences(of: "_", with: " ")): \(factText($0, values[$0]!, system: system))" }.joined(separator: "; ") }
            if case .array(let values) = value { return values.map { factText(key, $0, system: system) }.joined(separator: "; ") }
            return value.display
        }
        if key.hasSuffix("_minutes") { return WonderAnalysisRenderer.duration(number) + " min" }
        if key.hasSuffix("_ml") {
            return system.volumeFact(number, key: key)
        }
        if key.hasSuffix("_c") { return system.number(number, quantity: .temperature) + " " + system.symbol(for: .temperature) }
        if key.hasSuffix("_kg") { return system.number(number, quantity: .mass) + " " + system.symbol(for: .mass) }
        let unit: String
        if key.hasSuffix("_ml") { unit = " mL" }
        else if key.hasSuffix("_mg") { unit = " mg" }
        else if key.hasSuffix("_minutes") { unit = " min" }
        else if key.hasSuffix("_c") { unit = " °C" }
        else if key.hasSuffix("_percent") { unit = "%" }
        else { unit = "" }
        let display = ["_mg", "_c", "_minutes", "_percent"].contains(where: key.hasSuffix)
            ? number.formatted(.number.precision(.fractionLength(0...1))) : value.display
        return display + unit
    }
}
