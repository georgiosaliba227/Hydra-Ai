import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var units = DisplayUnits()
    @State private var showingCameraManualLog = false
    @State private var showingGoalSetup = false
    @AppStorage(GoalSetupPresentation.reviewKey) private var goalSetupReviewed = false

    var body: some View {
        TabView {
            NavigationStack {
                DashboardView()
            }
            .tabItem { Label("Today", systemImage: "drop.fill") }

            NavigationStack {
                HistoryView()
            }
            .tabItem { Label("History", systemImage: "calendar") }

            NavigationStack {
                InsightsView()
            }
            .tabItem { Label("Insights", systemImage: "sparkles") }

            NavigationStack {
                CameraCaptureView(onLogManually: { showingCameraManualLog = true })
            }
            .tabItem { Label("Camera", systemImage: "camera") }

            // Apple Health access now lives in Settings and on the Insights tab.
            NavigationStack { BackendSettingsView() }
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .tint(.hydraTint)
        .sheet(isPresented: $showingCameraManualLog) {
            NavigationStack { ManualLogView() }
        }
        .sheet(isPresented: $showingGoalSetup, onDismiss: { goalSetupReviewed = true }) {
            NavigationStack {
                GuidedGoalSetupView(profileStore: store.goalProfiles, onConfirmed: {
                    goalSetupReviewed = true; showingGoalSetup = false
                })
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Not now") { goalSetupReviewed = true; showingGoalSetup = false }
                            .accessibilityIdentifier("skipGoalSetup")
                    }
                }
            }
        }
        .environmentObject(units)
        .onChange(of: store.state) { _, _ in considerGoalSetup() }
        .onChange(of: store.configurationGeneration) { _, _ in showingGoalSetup = false }
        .onAppear { considerGoalSetup() }
    }

    private func considerGoalSetup() {
        #if DEBUG
        if ProcessInfo.processInfo.environment["HYDRA_TEST_SKIP_GOAL_SETUP"] == "1" { return }
        #endif
        guard store.state == .loaded, store.isConfigured, !store.configuration.offline, !goalSetupReviewed else { return }
        if store.summary?.goal != nil { goalSetupReviewed = true; return }
        guard !showingCameraManualLog else { return }
        showingGoalSetup = true
    }
}

private enum GoalSetupPresentation {
    static var reviewKey: String {
        #if DEBUG
        if let suite = ProcessInfo.processInfo.processInfoEnvironmentGoalSuite {
            return "hydra.goalSetupReviewed.v1.\(suite)"
        }
        #endif
        return "hydra.goalSetupReviewed.v1"
    }
}

#if DEBUG
private extension ProcessInfo {
    var processInfoEnvironmentGoalSuite: String? {
        guard let suite = environment["HYDRA_TEST_GOAL_PROFILE_SUITE"], suite.hasPrefix("HydraUITests."),
              UUID(uuidString: String(suite.suffix(36))) != nil else { return nil }
        return suite
    }
}
#endif
