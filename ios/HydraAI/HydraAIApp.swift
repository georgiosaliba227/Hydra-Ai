import SwiftUI

@main
struct HydraAIApp: App {
    @StateObject private var beverageStore = BeverageStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(beverageStore)
        }
    }
}
