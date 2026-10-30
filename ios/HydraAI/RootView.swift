import SwiftUI

struct RootView: View {
    @State private var showingCameraManualLog = false

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
    }
}
