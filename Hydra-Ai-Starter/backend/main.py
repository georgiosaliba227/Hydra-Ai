from fastapi import FastAPI
from pydantic import BaseModel, Field
from ai.forecast import estimate

app = FastAPI(title="Hydra AI Prototype API", version="0.1.0")

class ForecastRequest(BaseModel):
    weight_kg: float = Field(ge=20, le=300)
    exercise_minutes: int = Field(default=0, ge=0, le=600)
    hot_weather: bool = False

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/forecast")
def forecast(request: ForecastRequest):
    return estimate(request.weight_kg, request.exercise_minutes, request.hot_weather).__dict__
