import BackgroundTasks
import Foundation

@MainActor
enum DailyContextBackgroundRefresh {
    static let identifier = "com.georgiosaliba.hydraai.dailycontext"

    static func schedule(_ context: DailyContextCoordinator) {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
        guard context.healthAutoEnabled || context.weatherAutoEnabled else { return }
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = max(Date().addingTimeInterval(60), context.nextRefreshDate)
        // Availability, power and user settings are controlled by iOS. Foreground
        // refresh and actual last-success times remain the reliable UI contract.
        try? BGTaskScheduler.shared.submit(request)
    }
}
