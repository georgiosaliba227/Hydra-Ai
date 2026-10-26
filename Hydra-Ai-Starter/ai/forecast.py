"""Transparent demo fluid-intake estimator. Not medical advice."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Forecast:
    target_ml: int
    baseline_ml: int
    exercise_adjustment_ml: int
    explanation: str


def estimate(weight_kg: float, exercise_minutes: int = 0, hot_weather: bool = False) -> Forecast:
    if not 20 <= weight_kg <= 300:
        raise ValueError("weight_kg must be between 20 and 300")
    if not 0 <= exercise_minutes <= 600:
        raise ValueError("exercise_minutes must be between 0 and 600")
    # Prototype heuristics, deliberately not a validated clinical prescription.
    baseline = round(weight_kg * 30)
    exercise = round(exercise_minutes * 6)
    heat = 250 if hot_weather else 0
    total = baseline + exercise + heat
    return Forecast(
        target_ml=total,
        baseline_ml=baseline,
        exercise_adjustment_ml=exercise + heat,
        explanation=("Illustrative estimate from body weight, planned exercise, and heat. "
                     "Actual needs vary with sweat loss, diet, illness, and other factors; "
                     "do not force fluids to meet this number."),
    )
