import SwiftUI

struct RootView: View {
    @State private var selectedTab = 0
    @State private var showingCameraManualLog = false

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                DashboardView(onScan: { selectedTab = 3 })
            }
            .tabItem { Label("Today", systemImage: "drop.fill") }
            .tag(0)

            NavigationStack {
                HistoryView()
            }
            .tabItem { Label("History", systemImage: "calendar") }
            .tag(1)

            NavigationStack {
                InsightsView()
            }
            .tabItem { Label("Insights", systemImage: "sparkles") }
            .tag(2)

            NavigationStack {
                CameraCaptureView(onLogManually: { showingCameraManualLog = true })
            }
            .tabItem { Label("Camera", systemImage: "camera") }
            .tag(3)

            // Apple Health access now lives in Settings and on the Insights tab.
            NavigationStack { BackendSettingsView() }
                .tabItem { Label("Settings", systemImage: "gearshape") }
            .tag(4)
        }
        .tint(.hydraTint)
        .sheet(isPresented: $showingCameraManualLog) {
            NavigationStack { ManualLogView() }
        }
    }
}
