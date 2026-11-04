import SwiftUI

/// Demo has separate controllers so its result can never replace a personal draft.
struct WorkoutDemoView: View {
    @EnvironmentObject private var store: BeverageStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var controller = WorkoutForecastController()
    @StateObject private var wonder = RecordedWonderController()
    @State private var requestTask: Task<Void, Never>?
    @State private var wonderTask: Task<Void, Never>?
    private var connected: Bool { store.isConfigured && !store.isOffline }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                if let result = controller.result {
                    WorkoutResultView(result: result)
                } else {
                    Text("Explore a simulated workout").font(.title2.bold())
                    Text("Uses a fixed example, never your measurements or drink log.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    Button { run() } label: {
                        Label("Run the demo workout", systemImage: "play.fill")
                            .frame(maxWidth: .infinity, minHeight: 30)
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!connected || controller.state == .loading)
                    .accessibilityIdentifier("runWorkoutDemo")
                    if controller.state == .loading { ProgressView("Calculating the simulated workout…") }
                    if case .failed(let message) = controller.state { StatusBanner(text: message) }
                    if !connected { InfoNote("Connect in Settings to run this example.", systemImage: "link") }
                }
                HydraDisclosure(title: "Recorded Muse explanation", systemImage: "sparkles", identifier: "recordedWorkoutExplanation") {
                    Text("An earlier recorded response about this demo. Nothing is sent to Meta; the numbers are Hydra's.")
                    Button("Load recorded explanation") { loadWonder() }
                        .frame(minHeight: 44)
                        .disabled(!connected || wonder.state == .loading)
                        .accessibilityIdentifier("loadRecordedWonder")
                    if let recorded = wonder.result, let interpretation = recorded.systems["B"]?.interpretation {
                        Text("RECORDED · simulated workout").font(.headline)
                        WorkoutInterpretationView(interpretation: interpretation)
                        HydraDisclosure(title: "How this was made") {
                            let observed = recorded.provider_observations
                            if let input = observed["input_tokens"] ?? nil, let output = observed["output_tokens"] ?? nil,
                               let latency = observed["latency_ms"] ?? nil, let cost = observed["usage_derived_cost_micro_usd"] ?? nil {
                                Text("\(Int(input)) input · \(Int(output)) output tokens · \(Int(latency)) ms")
                                    .accessibilityIdentifier("recordedWonderUsage")
                                Text("Usage-derived cost \(HydraFormat.usd(micro: cost)); final billing pending.")
                            }
                            Text("Muse Wonder 1.0 · attempt \(recorded.provenance.attempt_id ?? "")")
                        }
                    }
                    if wonder.state == .loading { ProgressView() }
                    if case .failed(let message) = wonder.state { Text(message) }
                }
            }
            .hydraScreen()
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Demo workout").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Close") { dismiss() }.accessibilityIdentifier("closeWorkoutDemo")
            }
        }
        .onDisappear { requestTask?.cancel(); wonderTask?.cancel(); controller.invalidate(); wonder.invalidate() }
    }

    private func run() {
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        requestTask?.cancel()
        requestTask = Task { await controller.load(.demonstration(timezone: TimeZone.current.identifier), service: service) }
    }
    private func loadWonder() {
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        wonderTask?.cancel()
        wonderTask = Task { await wonder.load(service: service) }
    }
}
