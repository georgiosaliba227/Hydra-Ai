import SwiftUI

@main
@MainActor
struct HydraAIApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var beverageStore: BeverageStore

    init() {
        var configuration = APIConfiguration.load()
        if DemoAccount.isActive {
            configuration.onDevice = true
            #if DEBUG
            let environment = ProcessInfo.processInfo.environment
            if environment["HYDRA_TEST_BACKEND_URL"] != nil && environment["HYDRA_TEST_API_TOKEN"] != nil {
                configuration.insightsEnabled = true
            }
            #endif
        }
        _beverageStore = StateObject(wrappedValue: BeverageStore(configuration: configuration))
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if DemoAccount.isActive { DemoAccountView() }
                else { RootView() }
            }
            .environmentObject(beverageStore)
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { Task { await beverageStore.refresh() } }
            }
        }
    }
}
