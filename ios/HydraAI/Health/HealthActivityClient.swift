import Foundation
import HealthKit

/// An on-device activity aggregate. It has no direct hydration interpretation.
struct LocalActivitySummary: Equatable {
    let localDay: Date
    let timeZoneIdentifier: String
    /// Nil means Health returned no sample data; it does not mean zero steps.
    let stepCount: Int?
}

enum HealthActivityError: LocalizedError {
    case unavailable
    case invalidDay
    case invalidAggregate

    var errorDescription: String? {
        switch self {
        case .unavailable:
            return "Health data is unavailable on this device."
        case .invalidDay:
            return "The selected day could not be read."
        case .invalidAggregate:
            return "Health returned an invalid activity total."
        }
    }
}

@MainActor
protocol HealthActivityClient {
    var isAvailable: Bool { get }

    /// Call only following an explicit user action. Apple does not reveal whether read access was denied.
    func requestReadAccess() async throws

    /// Returns an aggregate for a calendar day in the caller's local timezone.
    func activity(on date: Date, calendar: Calendar) async throws -> LocalActivitySummary
}

/// Reads a single, limited HealthKit type. No raw samples are persisted or exported.
@MainActor
final class HealthKitActivityClient: HealthActivityClient {
    private let healthStore = HKHealthStore()

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestReadAccess() async throws {
        guard isAvailable else { throw HealthActivityError.unavailable }
        guard let stepType = HKObjectType.quantityType(forIdentifier: .stepCount) else {
            throw HealthActivityError.unavailable
        }
        try await healthStore.requestAuthorization(toShare: [], read: [stepType])
    }

    func activity(on date: Date, calendar: Calendar = .current) async throws -> LocalActivitySummary {
        guard isAvailable else { throw HealthActivityError.unavailable }
        guard let interval = calendar.dateInterval(of: .day, for: date),
              let stepType = HKObjectType.quantityType(forIdentifier: .stepCount) else {
            throw HealthActivityError.invalidDay
        }

        let predicate = HKQuery.predicateForSamples(
            withStart: interval.start,
            end: interval.end,
            options: []
        )
        let steps: Int? = try await withCheckedThrowingContinuation { continuation in
            let query = HKStatisticsQuery(
                quantityType: stepType,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, statistics, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                guard let quantity = statistics?.sumQuantity() else {
                    continuation.resume(returning: nil)
                    return
                }
                let value = quantity.doubleValue(for: .count())
                guard value.isFinite, value >= 0, value <= Double(Int.max) else {
                    continuation.resume(throwing: HealthActivityError.invalidAggregate)
                    return
                }
                continuation.resume(returning: Int(value.rounded()))
            }
            healthStore.execute(query)
        }

        return LocalActivitySummary(
            localDay: interval.start,
            timeZoneIdentifier: calendar.timeZone.identifier,
            stepCount: steps
        )
    }
}

/// For previews and tests only; it performs no HealthKit authorization or reads.
@MainActor
final class MockHealthActivityClient: HealthActivityClient {
    var isAvailable: Bool
    var sampleStepCount: Int?

    init(isAvailable: Bool = true, sampleStepCount: Int? = nil) {
        self.isAvailable = isAvailable
        self.sampleStepCount = sampleStepCount
    }

    func requestReadAccess() async throws {
        guard isAvailable else { throw HealthActivityError.unavailable }
    }

    func activity(on date: Date, calendar: Calendar = .current) async throws -> LocalActivitySummary {
        guard isAvailable else { throw HealthActivityError.unavailable }
        guard let interval = calendar.dateInterval(of: .day, for: date) else {
            throw HealthActivityError.invalidDay
        }
        return LocalActivitySummary(
            localDay: interval.start,
            timeZoneIdentifier: calendar.timeZone.identifier,
            stepCount: sampleStepCount
        )
    }
}
