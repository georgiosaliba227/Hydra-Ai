import Foundation

struct WorkoutDraft: Equatable {
    var activity = "running"
    var intensity = "moderate"
    var duration = ""
    var temperature = ""
    var humidity = ""
    var startsAt = Date.now.addingTimeInterval(3600)
    var comparable = false
    var consent = false
    var observedAt = Date.now.addingTimeInterval(-86400)
    var preMass = ""
    var postMass = ""
    var consumed = ""
    var urine = ""
    var measuredDuration = ""
    var massError = ""
    var intakeError = ""
    var urineError = ""
    var durationError = ""
    var protocolConfirmed = false

    static let activities = ["running", "cycling", "walking", "strength", "other"]
    static let intensities = ["low", "moderate", "high"]

    /// Fills step 1 from a workout the user picked (e.g. their last Apple Health workout).
    mutating func applyWorkout(activity: String, intensity: String?, durationMinutes: Double) {
        if Self.activities.contains(activity) { self.activity = activity }
        if let intensity, Self.intensities.contains(intensity) { self.intensity = intensity }
        duration = durationMinutes.formatted(.number.precision(.fractionLength(0...1)).grouping(.never))
    }

    /// Fills step 2 from a weather reading the user asked for.
    mutating func applyWeather(temperatureC: Double, humidityPercent: Double) {
        temperature = temperatureC.formatted(.number.precision(.fractionLength(0...1)).grouping(.never))
        humidity = humidityPercent.formatted(.number.precision(.fractionLength(0)).grouping(.never))
    }

    struct InputError: Error {
        let field: String
        let message: String
    }

    private func number(_ text: String, minimum: Double = 0, maximum: Double, field: String = "Value") throws -> Double {
        guard let value = Double(text), value.isFinite, value >= minimum, value <= maximum else {
            throw InputError(field: field, message: "Enter \(field.lowercased()) from \(minimum.formatted()) to \(maximum.formatted()).")
        }
        return value
    }
    func conditions() throws -> WorkoutForecastRequest.Conditions {
        try .init(activity: activity, intensity: intensity,
                  temperature_c: number(temperature, minimum: -60, maximum: 60, field: "Temperature"),
                  humidity_percent: number(humidity, maximum: 100, field: "Humidity"))
    }
    func exercise() throws -> WorkoutForecastRequest.Exercise {
        guard startsAt > .now else { throw ServiceError.invalidResponse }
        return try .init(event_id: UUID(), starts_at: ISO8601DateFormatter().string(from: startsAt),
                         duration_minutes: number(duration, minimum: 0.01, maximum: 1440),
                         conditions: conditions(), comparable_conditions_confirmed: comparable)
    }
    func sample() throws -> WorkoutForecastRequest.Sample {
        guard DateBoundary.onOrBefore(observedAt, .now) else {
            throw InputError(field: "Finished", message: "Choose a completed workout, not a future date.")
        }
        let pre = try number(preMass, minimum: 0.01, maximum: 500, field: "Weight before")
        let post = try number(postMass, minimum: 0.01, maximum: 500, field: "Weight after")
        let intake = try number(consumed, maximum: 50000, field: "Drank during")
        let urineVolume = try number(urine, maximum: 50000, field: "Urine during")
        let duration = try number(measuredDuration, minimum: 0.01, maximum: 1440, field: "Measured duration")
        let massBound = try number(massError, maximum: 500, field: "Each weighing ±")
        let intakeBound = try number(intakeError, maximum: 50000, field: "Amount drunk ±")
        let urineBound = try number(urineError, maximum: 50000, field: "Urine ±")
        let durationBound = try number(durationError, maximum: 1440, field: "Duration ±")
        guard durationBound < duration else {
            throw InputError(field: "Duration ±", message: "The duration error must be smaller than the measured duration.")
        }
        guard protocolConfirmed else {
            throw InputError(field: "Protocol", message: "Confirm comparable dry weighing and complete intake and urine records.")
        }
        return try .init(event_id: UUID(), observed_at: ISO8601DateFormatter().string(from: observedAt), conditions: conditions(),
            measurement: .init(pre_mass_kg: pre, post_mass_kg: post, consumed_ml: intake,
                urine_ml: urineVolume, duration_minutes: duration),
            errors: .init(pre_mass_kg: massBound, post_mass_kg: massBound,
                consumed_ml: intakeBound, urine_ml: urineBound, duration_minutes: durationBound))
    }
}
