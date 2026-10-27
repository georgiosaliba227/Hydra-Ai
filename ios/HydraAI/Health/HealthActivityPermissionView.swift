import SwiftUI

/// Optional activity access. The button is the only place that requests Health permission.
@MainActor
struct HealthActivityPermissionView: View {
    private let client: any HealthActivityClient

    @State private var isLoading = false
    @State private var hasRequestedAccess = false
    @State private var summary: LocalActivitySummary?
    @State private var errorMessage: String?

    init() {
        self.client = HealthKitActivityClient()
    }

    init(client: any HealthActivityClient) {
        self.client = client
    }

    var body: some View {
        Form {
            Section("Apple Health") {
                Text("You can optionally read today's step total on this device. Activity data is not used to diagnose dehydration or calculate a fluid target.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                if client.isAvailable {
                    Button {
                        Task { await requestAndRead() }
                    } label: {
                        Label(
                            hasRequestedAccess ? "Read today's steps again" : "Choose Health access",
                            systemImage: "heart.text.square"
                        )
                    }
                    .disabled(isLoading)
                } else {
                    Text("Health data is unavailable on this device. Manual beverage logging remains available.")
                        .foregroundStyle(.secondary)
                }

                if isLoading {
                    ProgressView("Reading on-device activity")
                }

                if let summary {
                    if let stepCount = summary.stepCount {
                        LabeledContent("Today's steps", value: stepCount.formatted())
                    } else {
                        Text("No step total was returned. This can mean there are no samples or Health access was declined.")
                            .foregroundStyle(.secondary)
                    }
                }

                if let errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .accessibilityAddTraits(.updatesFrequently)
                }
            }

            Section {
                Text("Only the daily total is shown here. Raw Health records stay on your iPhone, and no activity is sent to the backend.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Health access")
    }

    private func requestAndRead() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            try await client.requestReadAccess()
            hasRequestedAccess = true
            summary = try await client.activity(on: Date(), calendar: .current)
        } catch {
            summary = nil
            errorMessage = error.localizedDescription
        }
    }
}
