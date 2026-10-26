import SwiftUI

struct ContentView: View {
    @State private var consumedML = 750
    private let targetML = 2400 // Demo only; replace with backend estimate.

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Image(systemName: "drop.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(.cyan)
                Text("Today's hydration")
                    .font(.title2.bold())
                Text("\(consumedML) / \(targetML) mL")
                    .font(.title.bold())
                ProgressView(value: min(Double(consumedML) / Double(targetML), 1))
                    .tint(.cyan)
                Button("Log 250 mL water") { consumedML += 250 }
                    .buttonStyle(.borderedProminent)
                Text("Prototype only. Goals are illustrative and not medical advice.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Spacer()
            }
            .padding()
            .navigationTitle("Hydra AI")
        }
    }
}
