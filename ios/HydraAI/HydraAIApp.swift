import SwiftUI

@main
@MainActor
struct HydraAIApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var beverageStore = BeverageStore()
    @StateObject private var units = DisplayUnits()
    @StateObject private var dailyContext: DailyContextCoordinator

    init() {
        var defaults = UserDefaults.standard
        #if DEBUG
        if let suite = ProcessInfo.processInfo.environment["HYDRA_TEST_CONTEXT_SUITE"],
           suite.hasPrefix("HydraUITests."), let isolated = UserDefaults(suiteName: suite) {
            defaults = isolated
        }
        #endif
        let context = DailyContextCoordinator.live(defaults: defaults)
        #if DEBUG
        if ProcessInfo.processInfo.environment["HYDRA_TEST_CONTEXT_SETUP"] == "skip" {
            context.completeSetup()
        }
        #endif
        _dailyContext = StateObject(wrappedValue: context)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(beverageStore)
                .environmentObject(units)
                .environmentObject(dailyContext)
                .environmentObject(dailyContext.workoutContext)
                .task { await refreshContext() }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await beverageStore.refresh(); await refreshContext() }
                    } else if phase == .background { DailyContextBackgroundRefresh.schedule(dailyContext) }
                }
                .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { _ in
                    if scenePhase == .active { Task { await refreshContext() } }
                }
                .onReceive(NotificationCenter.default.publisher(for: .NSCalendarDayChanged)) { _ in
                    if scenePhase == .active { Task { await refreshContext() } }
                }
                .onReceive(NotificationCenter.default.publisher(for: .NSSystemTimeZoneDidChange)) { _ in
                    if scenePhase == .active { Task { await refreshContext() } }
                }
        }
        .backgroundTask(.appRefresh(DailyContextBackgroundRefresh.identifier)) { [dailyContext] in
            await withTaskCancellationHandler {
                await dailyContext.refreshIfNeeded(mode: .background)
                await MainActor.run { DailyContextBackgroundRefresh.schedule(dailyContext) }
            } onCancel: {
                Task { @MainActor in dailyContext.cancelRefresh() }
            }
        }
    }

    private func refreshContext() async {
        await dailyContext.refreshIfNeeded()
        DailyContextBackgroundRefresh.schedule(dailyContext)
    }
}
