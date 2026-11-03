import XCTest
@testable import HydraAI

final class AutomaticWorkoutApplicationTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_793_700_000)

    private func suggestion(requested: Date, hour: Date) -> WorkoutContextDraft {
        var value = WorkoutContextDraft()
        value.temperatureC = 10; value.humidityPercent = 70
        value.weatherProvenance = "Weather from Open-Meteo for your area"
        value.weatherRequestedTime = requested; value.weatherForecastHour = hour
        return value
    }

    func testWrongRequestedTimeDoesNotFillAnyFields() {
        var draft = WorkoutDraft(); draft.startsAt = start
        let original = draft
        draft.applyWeatherSuggestion(suggestion(requested: start.addingTimeInterval(3600), hour: start))
        XCTAssertEqual(draft, original)
    }

    func testWrongForecastHourDoesNotFillAnyFields() {
        var draft = WorkoutDraft(); draft.startsAt = start
        let original = draft
        draft.applyWeatherSuggestion(suggestion(requested: start, hour: start.addingTimeInterval(90 * 60 + 1)))
        XCTAssertEqual(draft, original)
    }

    func testMatchingWeatherStaysCanonicalAndCarriesHour() {
        var draft = WorkoutDraft(); draft.startsAt = start
        let original = draft
        XCTAssertTrue(draft.applyAutomaticWeather(suggestion(requested: start, hour: start), unchangedSince: original))
        XCTAssertEqual(draft.temperature, "10")
        XCTAssertEqual(draft.humidity, "70")
        XCTAssertEqual(draft.appliedWeather?.forecastHour, start)
        XCTAssertNotNil(draft.weatherProvenance)
    }

    func testChangingStartRemovesApplicabilityAndCanClearOnlyAppliedValues() {
        var draft = WorkoutDraft(); draft.startsAt = start
        draft.applyWeatherSuggestion(suggestion(requested: start, hour: start))
        draft.startsAt = start.addingTimeInterval(3600)
        XCTAssertNil(draft.weatherProvenance)
        draft.clearAppliedWeather()
        XCTAssertEqual(draft.temperature, ""); XCTAssertEqual(draft.humidity, "")
        XCTAssertNil(draft.appliedWeather)
    }

    func testWeatherClearPreservesManuallyEditedConditions() {
        var draft = WorkoutDraft(); draft.startsAt = start
        draft.applyWeatherSuggestion(suggestion(requested: start, hour: start))
        draft.temperature = "12"
        draft.clearAppliedWeather()
        XCTAssertEqual(draft.temperature, "12"); XCTAssertEqual(draft.humidity, "70")
    }

    func testDelayedWeatherCannotOverwriteAnyEditedForm() {
        var draft = WorkoutDraft(); draft.startsAt = start
        let original = draft
        draft.duration = "42"
        let edited = draft
        XCTAssertFalse(draft.applyAutomaticWeather(suggestion(requested: start, hour: start), unchangedSince: original))
        XCTAssertEqual(draft, edited)
    }

    func testDelayedWorkoutCannotOverwriteEditedActivity() {
        var draft = WorkoutDraft(); let original = draft
        draft.activity = "walking"
        var suggestion = WorkoutContextDraft()
        suggestion.activity = "cycling"; suggestion.durationMinutes = 50
        suggestion.workoutProvenance = "Sample workout (not your data)"
        XCTAssertFalse(draft.applyAutomaticWorkout(suggestion, unchangedSince: original))
        XCTAssertEqual(draft.activity, "walking"); XCTAssertEqual(draft.duration, "")
    }
}
