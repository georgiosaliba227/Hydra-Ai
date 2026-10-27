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
            .tabItem { Label("History", systemImage: "clock.arrow.circlepath") }

            NavigationStack {
                CameraCaptureView(onLogManually: { showingCameraManualLog = true })
            }
            .tabItem { Label("Camera", systemImage: "camera") }

            NavigationStack {
                HealthActivityPermissionView()
            }
            .tabItem { Label("Health", systemImage: "heart.text.square") }
        }
        .sheet(isPresented: $showingCameraManualLog) {
            NavigationStack { ManualLogView() }
        }
    }
}
