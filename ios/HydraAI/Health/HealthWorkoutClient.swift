import Foundation
import HealthKit

/// The activity values accepted by the workout forecast contract
/// (`backend/personal_forecasts.py` `ConditionsInput.activity`).
enum WorkoutForecastActivity: String, CaseIterable, Sendable {
    case running, cycling, walking, strength, other
}

/// How an Apple Health workout type was translated to a forecast activity.
struct WorkoutActivityMapping: Equatable, Sendable {
    let activity: WorkoutForecastActivity
    /// Human-readable Apple Health type, for example "Yoga".
    let healthTypeName: String
    /// False when the Health type has no direct forecast equivalent and the safe default `other` was used.
    let isDirectMatch: Bool

    /// Shown next to a prefilled activity when the mapping was not direct.
    var note: String? {
        isDirectMatch ? nil : "Apple Health type \"\(healthTypeName)\" has no direct match here, so Other is used. Change it if another activity fits better."
    }

    /// Unknown or unlisted types map to `.other`, which the forecast always accepts.
    static func map(_ type: HKWorkoutActivityType) -> WorkoutActivityMapping {
        let name = healthTypeName(type)
        switch type {
        case .running:
            return .init(activity: .running, healthTypeName: name, isDirectMatch: true)
        case .cycling:
            return .init(activity: .cycling, healthTypeName: name, isDirectMatch: true)
        case .walking, .hiking:
            return .init(activity: .walking, healthTypeName: name, isDirectMatch: true)
        case .traditionalStrengthTraining, .functionalStrengthTraining:
            return .init(activity: .strength, healthTypeName: name, isDirectMatch: true)
        default:
            return .init(activity: .other, healthTypeName: name, isDirectMatch: false)
        }
    }

    static func healthTypeName(_ type: HKWorkoutActivityType) -> String {
        switch type {
        case .running: "Running"
        case .cycling: "Cycling"
        case .walking: "Walking"
        case .hiking: "Hiking"
        case .traditionalStrengthTraining: "Traditional strength training"
        case .functionalStrengthTraining: "Functional strength training"
        case .swimming: "Swimming"
        case .yoga: "Yoga"
        case .highIntensityIntervalTraining: "High-intensity interval training"
        case .elliptical: "Elliptical"
        case .rowing: "Rowing"
        case .stairClimbing: "Stair climbing"
        case .coreTraining: "Core training"
        case .dance: "Dance"
        case .soccer: "Soccer"
        case .basketball: "Basketball"
        case .tennis: "Tennis"
        case .crossTraining: "Cross training"
        case .mixedCardio: "Mixed cardio"
        case .pilates: "Pilates"
        case .other: "Other"
        default: "Workout"
        }
    }
}

/// One Apple Health workout, reduced to the fields the forecast form can use.
/// Kept in memory on device only; it is never persisted or uploaded.
struct HealthWorkoutSummary: Equatable, Identifiable, Sendable {
    enum Source: Equatable, Sendable {
        case appleHealth
        /// Built-in sample data for previews, tests and the Simulator. Never the user's data.
        case sample
    }

    let id: UUID
    let source: Source
    let healthActivityTypeRawValue: UInt
    let mapping: WorkoutActivityMapping
    let startDate: Date
    let durationSeconds: TimeInterval
    /// Active energy recorded for this workout, if Health has it. Display context only.
    let activeEnergyKilocalories: Double?
    /// Average heart rate during the workout. Display context only: never a hydration signal.
    let averageHeartRateBPM: Double?

    var activity: WorkoutForecastActivity { mapping.activity }
    var durationMinutes: Double { durationSeconds / 60 }

    /// Accepts only values the forecast form could use; out-of-range Health values become nil or are rejected.
    init?(id: UUID, source: Source, activityType: HKWorkoutActivityType, startDate: Date,
          durationSeconds: TimeInterval, activeEnergyKilocalories: Double?, averageHeartRateBPM: Double?) {
        // The forecast accepts 0 < duration <= 1440 minutes.
        guard durationSeconds.isFinite, durationSeconds > 0, durationSeconds <= 1440 * 60 else { return nil }
        self.id = id
        self.source = source
        self.healthActivityTypeRawValue = activityType.rawValue
        self.mapping = WorkoutActivityMapping.map(activityType)
        self.startDate = startDate
        self.durationSeconds = durationSeconds
        self.activeEnergyKilocalories = activeEnergyKilocalories.flatMap { $0.isFinite && $0 >= 0 && $0 <= 20_000 ? $0 : nil }
        self.averageHeartRateBPM = averageHeartRateBPM.flatMap { $0.isFinite && $0 >= 20 && $0 <= 260 ? $0 : nil }
    }
}

/// Typical sessions, computed on device from the workouts passed in.
struct TypicalWorkoutSessions: Equatable, Sendable {
    let sessionCount: Int
    let medianDurationMinutes: Double?
    let mostCommonActivity: WorkoutForecastActivity?
    let mostCommonActivityCount: Int
    let earliestStart: Date?
    let latestStart: Date?

    /// Median duration; most common mapped activity, ties broken by the most recent workout.
    static func summarize(_ workouts: [HealthWorkoutSummary]) -> TypicalWorkoutSessions {
        guard !workouts.isEmpty else {
            return .init(sessionCount: 0, medianDurationMinutes: nil, mostCommonActivity: nil,
                         mostCommonActivityCount: 0, earliestStart: nil, latestStart: nil)
        }
        let durations = workouts.map(\.durationMinutes).sorted()
        let middle = durations.count / 2
        let median = durations.count.isMultiple(of: 2) ? (durations[middle - 1] + durations[middle]) / 2 : durations[middle]

        var counts: [WorkoutForecastActivity: Int] = [:]
        var latest: [WorkoutForecastActivity: Date] = [:]
        for workout in workouts {
            counts[workout.activity, default: 0] += 1
            latest[workout.activity] = max(latest[workout.activity] ?? .distantPast, workout.startDate)
        }
        let top = counts.max { lhs, rhs in
            lhs.value != rhs.value ? lhs.value < rhs.value : (latest[lhs.key] ?? .distantPast) < (latest[rhs.key] ?? .distantPast)
        }
        let starts = workouts.map(\.startDate)
        return .init(sessionCount: workouts.count, medianDurationMinutes: median, mostCommonActivity: top?.key,
                     mostCommonActivityCount: top?.value ?? 0, earliestStart: starts.min(), latestStart: starts.max())
    }

    /// For example: "Typical session: 45 min of running (6 of your last 9 workouts)".
    var displayText: String? {
        guard sessionCount > 0, let medianDurationMinutes, let mostCommonActivity else { return nil }
        let minutes = Int(medianDurationMinutes.rounded())
        return "Typical session: \(minutes) min; most often \(mostCommonActivity.rawValue) (\(mostCommonActivityCount) of your last \(sessionCount) workouts)"
    }
}

enum HealthWorkoutError: LocalizedError, Equatable {
    case unavailable
    case noWorkouts

    var errorDescription: String? {
        switch self {
        case .unavailable:
            return "Health data is unavailable on this device. You can still enter the workout yourself."
        case .noWorkouts:
            return "No recent workouts were found. This can mean there are none in Health or access was not allowed. You can still enter the workout yourself."
        }
    }
}

@MainActor
protocol HealthWorkoutClient: AnyObject {
    var isAvailable: Bool { get }

    /// Call only from an explicit user action. Requests read access to workouts, active energy and heart rate.
    /// Apple does not reveal whether read access was denied; denial looks like no data.
    func requestWorkoutReadAccess() async throws

    /// Most recent first, at most `limit` (clamped to 1...50). Read on device; nothing is stored or uploaded.
    func recentWorkouts(limit: Int) async throws -> [HealthWorkoutSummary]
}

extension HealthWorkoutClient {
    /// Computed on device from `recentWorkouts(limit:)`.
    func typicalSessions(limit: Int = 20) async throws -> TypicalWorkoutSessions {
        TypicalWorkoutSessions.summarize(try await recentWorkouts(limit: limit))
    }
}

/// Reads workouts plus their active energy and average heart rate. No raw samples are persisted or exported.
@MainActor
final class HealthKitWorkoutClient: HealthWorkoutClient {
    private let healthStore: HKHealthStore
    private let heartRateType = HKQuantityType(.heartRate)
    private let activeEnergyType = HKQuantityType(.activeEnergyBurned)

    init(healthStore: HKHealthStore = HKHealthStore()) {
        self.healthStore = healthStore
    }

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    /// The minimum set for this feature: workouts, active energy, heart rate. Nothing is written.
    var readTypes: Set<HKObjectType> { [HKObjectType.workoutType(), activeEnergyType, heartRateType] }

    func requestWorkoutReadAccess() async throws {
        guard isAvailable else { throw HealthWorkoutError.unavailable }
        try await healthStore.requestAuthorization(toShare: [], read: readTypes)
    }

    func recentWorkouts(limit: Int) async throws -> [HealthWorkoutSummary] {
        guard isAvailable else { throw HealthWorkoutError.unavailable }
        let descriptor = HKSampleQueryDescriptor(
            predicates: [.workout()],
            sortDescriptors: [SortDescriptor(\.startDate, order: .reverse)],
            limit: min(max(limit, 1), 50)
        )
        let workouts = try await descriptor.result(for: healthStore)
        var summaries: [HealthWorkoutSummary] = []
        for workout in workouts {
            let energy = workout.statistics(for: activeEnergyType)?.sumQuantity()?.doubleValue(for: .kilocalorie())
            var heartRate = workout.statistics(for: heartRateType)?.averageQuantity()?.doubleValue(for: Self.bpm)
            if heartRate == nil {
                heartRate = try? await averageHeartRate(from: workout.startDate, to: workout.endDate)
            }
            if let summary = HealthWorkoutSummary(
                id: workout.uuid, source: .appleHealth, activityType: workout.workoutActivityType,
                startDate: workout.startDate, durationSeconds: workout.duration,
                activeEnergyKilocalories: energy, averageHeartRateBPM: heartRate
            ) {
                summaries.append(summary)
            }
        }
        return summaries
    }

    private static let bpm = HKUnit.count().unitDivided(by: .minute())

    /// Fallback when the workout itself carries no heart-rate statistics.
    private func averageHeartRate(from start: Date, to end: Date) async throws -> Double? {
        let interval = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let descriptor = HKStatisticsQueryDescriptor(
            predicate: .quantitySample(type: heartRateType, predicate: interval),
            options: .discreteAverage
        )
        return try await descriptor.result(for: healthStore)?.averageQuantity()?.doubleValue(for: Self.bpm)
    }
}

/// Clearly labeled sample workouts for previews, tests and the Simulator (which has no Health workouts).
/// It performs no HealthKit authorization or reads.
@MainActor
final class SampleHealthWorkoutClient: HealthWorkoutClient {
    var isAvailable: Bool
    var workouts: [HealthWorkoutSummary]
    private(set) var accessRequests = 0
    private(set) var reads = 0

    init(isAvailable: Bool = true, workouts: [HealthWorkoutSummary]? = nil, now: Date = .now) {
        self.isAvailable = isAvailable
        self.workouts = workouts ?? Self.sampleWorkouts(endingAt: now)
    }

    func requestWorkoutReadAccess() async throws {
        accessRequests += 1
        guard isAvailable else { throw HealthWorkoutError.unavailable }
    }

    func recentWorkouts(limit: Int) async throws -> [HealthWorkoutSummary] {
        reads += 1
        guard isAvailable else { throw HealthWorkoutError.unavailable }
        return Array(workouts.sorted { $0.startDate > $1.startDate }.prefix(min(max(limit, 1), 50)))
    }

    static func sampleWorkouts(endingAt now: Date) -> [HealthWorkoutSummary] {
        let day: TimeInterval = 86_400
        let entries: [(HKWorkoutActivityType, TimeInterval, Double, Double?, Double?)] = [
            (.running, 1, 45, 480, 148),
            (.cycling, 3, 60, 520, 132),
            (.running, 5, 40, 430, 151),
            (.traditionalStrengthTraining, 6, 50, 260, nil),
            (.running, 8, 50, 530, 146),
        ]
        return entries.compactMap { type, daysAgo, minutes, energy, heartRate in
            HealthWorkoutSummary(id: UUID(), source: .sample, activityType: type,
                                 startDate: now.addingTimeInterval(-daysAgo * day), durationSeconds: minutes * 60,
                                 activeEnergyKilocalories: energy, averageHeartRateBPM: heartRate)
        }
    }
}
