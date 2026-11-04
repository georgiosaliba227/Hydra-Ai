import SwiftUI

/// Main result keeps the meaning and uncertainty beside the number.
struct WorkoutResultView: View {
    let result: WorkoutForecast

    var body: some View {
        VStack(alignment: .leading, spacing: HydraSpacing.section) {
            VStack(alignment: .leading, spacing: 10) {
                if result.synthetic {
                    Text("SIMULATED · not your measurements")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(Color.hydraTint)
                }
                if let value = result.valueMl, let lower = result.lowerMl, let upper = result.upperMl {
                    Text("Estimated sweat loss").font(.headline)
                    Text("\(HydraFormat.milliliters(value)) mL")
                        .font(.system(.largeTitle, design: .rounded).bold()).foregroundStyle(Color.hydraTint)
                        .accessibilityLabel("Estimated exercise sweat loss: \(HydraFormat.milliliters(value)) mL")
                        .accessibilityIdentifier("workoutPrediction")
                    Text("Range \(HydraFormat.milliliters(lower))–\(HydraFormat.milliliters(upper)) mL")
                        .font(.body.monospacedDigit())
                    Text(result.synthetic
                         ? "Range checked only on simulated data; it does not show accuracy for you."
                         : "Range reflects your measurement errors and comparable past workouts. Actual loss can differ.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if result.longitudinalHistory != nil {
                        Text("Recent-workout adaptation is experimental. This range is not a calibrated prediction interval.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                } else {
                    Text(result.synthetic ? "Demo unavailable" : "More measurements needed").font(.title2.bold())
                        .accessibilityIdentifier("workoutInsufficientData")
                    Text(result.synthetic
                         ? "The simulated example isn't available on this backend. You don't need to add personal measurements for the demo."
                         : "There isn't enough comparable data for a personal estimate yet.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if !result.synthetic, let missing = result.missingInputs, !missing.isEmpty {
                        Text("Needed: " + missing.map { $0.replacingOccurrences(of: "_", with: " ") }.joined(separator: ", "))
                            .font(.subheadline).accessibilityIdentifier("workoutMissingMeasurements")
                    }
                }
                InfoNote("Not a drinking target or a measure of hydration.")
            }
            .hydraCard(padding: 20)
            HydraDisclosure(title: "About this estimate", identifier: "workoutResultDetails") {
                LabeledContent("Data", value: result.dataSufficiency.replacingOccurrences(of: "_", with: " "))
                LabeledContent("Personalization", value: result.personalizationStatus.replacingOccurrences(of: "_", with: " "))
                LabeledContent("Measurements used", value: result.sampleCount.formatted())
                LabeledContent("Model", value: result.modelVersion)
                if let history = result.longitudinalHistory {
                    Text("\(history.comparable_samples) comparable of \(history.total_samples) supplied workouts; \(history.recent_samples) recent measurements.")
                        .accessibilityIdentifier("longitudinalHistory")
                    if let first = history.first_observed_at, let last = history.last_observed_at {
                        Text("Observation window (UTC): \(first) to \(last)")
                    }
                    Text("History is held for this session only.")
                }
                ForEach(result.inputFactors.keys.sorted(), id: \.self) { key in
                    if let factor = result.inputFactors[key] {
                        LabeledContent(key.replacingOccurrences(of: "_", with: " ").capitalized, value: factor.display)
                    }
                }
                ForEach(Array(result.provenance.enumerated()), id: \.offset) { _, source in Text(source) }
                ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, text in
                    Text(text.replacingOccurrences(of: "_", with: " "))
                }
            }
            if result.synthetic {
                HydraDisclosure(title: "Research details", systemImage: "testtube.2", identifier: "workoutResearchDetails") {
                    if let comparison = result.contextComparison, let interpretation = comparison.systems["B"]?.interpretation {
                        HydraDisclosure(title: "Compare A / B / C · research mock", identifier: "contextComparison") {
                            Text("A · Existing numerical estimate")
                            Text("B · Contextual mock; no numerical prediction")
                            Text("C · Same estimate plus contextual mock")
                            Text("No Meta response or billed request was observed. This mock cannot measure Muse Wonder's quality.")
                            WorkoutInterpretationView(interpretation: interpretation)
                            Text("Provider latency, tokens and actual cost: not observed.")
                        }
                    }
                    if let explanation = result.mockExplanation {
                        Text("Local explanation fixtures · mock only. No live Meta request was made.")
                        ForEach(Array(explanation.explanations.enumerated()), id: \.offset) { _, text in Text(text) }
                    }
                }
            }
        }
    }
}

struct WorkoutInterpretationView: View {
    let interpretation: HydrationContextComparison.Interpretation
    private let categories = ["factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions"]
    var body: some View {
        ForEach(categories, id: \.self) { category in
            if let texts = interpretation.reviewed_text[category], !texts.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(category.replacingOccurrences(of: "_", with: " ").capitalized).font(.headline)
                    ForEach(Array(texts.enumerated()), id: \.offset) { _, text in
                        Text(text).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}
