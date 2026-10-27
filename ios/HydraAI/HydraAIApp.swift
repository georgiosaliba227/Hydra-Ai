import SwiftUI

@main
struct HydraAIApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var beverageStore = BeverageStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(beverageStore)
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active { Task { await beverageStore.refresh() } }
                }
        }
    }
}
