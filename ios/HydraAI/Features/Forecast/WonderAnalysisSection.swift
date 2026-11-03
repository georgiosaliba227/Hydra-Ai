import SwiftUI

struct WonderAnalysisSection: View {
    @ObservedObject var controller: WonderAnalysisController
    @Binding var backendConsent: Bool
    @Binding var metaConsent: Bool
    let connected: Bool
    let prepare: () -> Void
    let explain: () -> Void
    var body: some View {
        Section {
            Text("Muse Wonder can select supported findings across your workout, logged intake, conditions and measurement history. Hydra calculates every number.")
                .font(.subheadline)
            Toggle("I consent to preparing this detailed summary on my backend", isOn: $backendConsent)
                .accessibilityIdentifier("richAnalysisBackendConsent")
            Button("Preview detailed Muse Wonder analysis", action: prepare)
                .disabled(!backendConsent || !connected || controller.state == .loading || controller.explaining)
                .accessibilityIdentifier("prepareRichAnalysis")
            Text("Uses the same reviewed manual inputs as your estimate, plus your backend's logged-drink aggregates. Preparing a preview makes no Meta request.")
                .font(.caption).foregroundStyle(.secondary)
            if controller.state == .loading { ProgressView("Preparing the detailed summary…") }
            if case .failed(let message) = controller.state { Text(message).font(.footnote).foregroundStyle(.secondary) }
            if let result = controller.result { resultContent(result) }
            if let preview = controller.preview {
                Text("What would be shared with Meta").font(.headline).accessibilityIdentifier("richAnalysisPreview")
                Text("Only these aggregate facts. No body weights, raw HealthKit records, precise location, beverage names, credentials or measurement dates.")
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(Self.groups, id: \.0) { key, title in
                    if let value = preview.facts.values[key] {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(title).font(.subheadline.weight(.semibold))
                            Text(Self.display(value)).font(.caption).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .accessibilityIdentifier("richAnalysisFacts-\(key)")
                    }
                }
                DisclosureGroup("Exact facts to be shared") {
                    Text(Self.json(preview.facts)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                }
                if let estimate = preview.worst_case_micro_usd {
                    Text("Reference cost estimate: \(HydraFormat.usd(micro: Double(estimate))).")
                        .font(.caption).accessibilityIdentifier("richAnalysisReferenceCost")
                    Text("Reference prices are not a verified live quote or final charge. Backend spending checks and the \(HydraFormat.usd(micro: Double(preview.per_request_cap_micro_usd))) request cap still apply.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if !preview.live_available || !preview.dispatch_supported {
                    Text("Detailed Muse Wonder analysis isn't enabled on this backend. Nothing can be sent to Meta from here.")
                        .font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("richAnalysisUnavailable")
                } else if !preview.explainable {
                    Text("More personal observations or logs are needed before requesting this explanation. Your local research analysis remains available.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if controller.isQuarantined {
                    Text("These facts were already attempted and may have been charged. They will not be sent again from this screen. Preparing a new preview can recover a saved result without another Meta request.")
                        .font(.footnote).foregroundStyle(.orange).accessibilityIdentifier("richAnalysisQuarantined")
                }
                if controller.canOffer {
                    Toggle("Send only this reviewed summary to Meta's Muse Wonder", isOn: $metaConsent)
                        .accessibilityIdentifier("richAnalysisMetaConsent")
                    Button("Explain my detailed analysis", action: explain)
                        .disabled(!metaConsent || !connected || controller.explaining)
                        .accessibilityIdentifier("explainRichAnalysis")
                }
            }
            if controller.explaining { ProgressView("Asking Muse Wonder once…") }
            if let error = controller.explainError { Text(error).font(.footnote).foregroundStyle(.orange) }
        } header: { Text("Detailed Muse Wonder analysis") }
        footer: { Text("Separate from the local research analysis and the workout-only explanation. Meta consent is requested for each new preview. No automatic requests or retries.") }
    }
    @ViewBuilder private func resultContent(_ result: WonderAnalysisResult) -> some View {
        Text(controller.replayed ? "Showing the saved analysis. No new Meta request or charge." : "Muse Wonder selected these supported findings. Hydra calculated every number.")
            .font(.subheadline.weight(.semibold)).accessibilityIdentifier("richAnalysisResult")
        ForEach(result.sections) { section in
            DisclosureGroup(section.title) {
                Text(localText(result, section)).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                ForEach(Array(section.insights.enumerated()), id: \.element.id) { index, insight in
                    Text("\(index + 1). \(insight.title)").font(.caption).foregroundStyle(.secondary)
                }
            }
            .accessibilityIdentifier("richAnalysisResult-\(section.id)")
        }
        DisclosureGroup("How this was made") {
            Text("Muse Wonder selected supported findings; Hydra supplied the wording and every number.")
            Text("Model: \(result.provenance.provider) · \(result.provenance.model)")
            Text("Account: \(result.provenance.account_id) · Attempt: \(result.provenance.attempt_id)")
            if let cost = result.provider_observations["usage_derived_cost_micro_usd"] ?? nil {
                Text("Usage-based cost estimate: \(HydraFormat.usd(micro: cost)). Final invoice pending.")
            }
            Text("Selection origin: \(result.provenance.selection_origin)")
            Text(controller.resultSaved ? "Saved on your backend for free replay of these exact facts." : "This result was not saved on your backend.")
            ForEach(Array(WonderAnalysisRenderer.liveLimitations.enumerated()), id: \.offset) { _, limitation in Text(limitation) }
        }
        .font(.caption).foregroundStyle(.secondary)
    }
    private func localText(_ result: WonderAnalysisResult, _ section: WonderAnalysisResult.Section) -> String {
        guard let values = try? WonderAnalysisRenderer.placeholders(result.facts) else { return "Validated analysis unavailable." }
        let templates = section.insights.compactMap { WonderAnalysisResult.insightContracts[section.id]?[$0.id]?.1 }
        let template = (templates + [WonderAnalysisRenderer.requiredCaveats[section.id] ?? ""]).joined(separator: " ")
        return WonderAnalysisRenderer.render(template, values: values)
    }
    private static let groups = [("forecast", "Research workout estimate"), ("intake", "Logged intake and documented composition"),
        ("activity", "Planned activity"), ("environment", "Environmental context"), ("calibration", "Comparable measurements"),
        ("trends", "Descriptive intake history"), ("accounting", "Exercise accounting"),
        ("workout_comparison", "Comparison with previous workouts"), ("trend_context", "Logged weekly and timing patterns"), ("missing_inputs", "Missing information")]
    private static func display(_ value: WonderAnalysisValue, key: String = "") -> String {
        switch value {
        case .null: return "Unknown / unavailable"
        case .flag(let value): return value ? "Yes" : "No"
        case .text(let value): return value.replacingOccurrences(of: "_", with: " ")
        case .number(let value):
            if key.hasSuffix("_minutes") { return WonderAnalysisRenderer.duration(value) + " min" }
            if key.hasSuffix("_ml") {
                let displayed = key.contains("lower_ml") ? floor(value) : key.contains("upper_ml") ? ceil(value) : value
                return HydraFormat.milliliters(displayed) + " mL"
            }
            let unit = key.hasSuffix("_mg") ? " mg" : key.hasSuffix("_c") ? " °C" : key.hasSuffix("_percent") || key == "change_pct" ? "%" : key.hasSuffix("_minutes") ? " min" : ""
            return value.formatted(.number.precision(.fractionLength(0...1))) + unit
        case .array(let values): return values.isEmpty ? "None" : values.map { display($0) }.joined(separator: "; ")
        case .object(let values): return values.keys.sorted().map { "\($0.replacingOccurrences(of: "_", with: " ").capitalized): \(display(values[$0]!, key: $0))" }.joined(separator: "\n")
        }
    }
    private static func json(_ facts: WonderAnalysisFacts) -> String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return (try? encoder.encode(facts)).map { String(decoding: $0, as: UTF8.self) } ?? "Exact facts unavailable; do not send."
    }
}
