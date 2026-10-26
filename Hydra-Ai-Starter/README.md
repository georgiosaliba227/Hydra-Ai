# Hydra AI

Personalized hydration forecasting for the Meta AI Developer Hackathon.

## MVP
- Log drinks and track daily fluid intake
- Estimate a baseline daily fluid target
- Adjust estimates using exercise and weather context
- Show transparent explanations and uncertainty
- Prepare for Apple HealthKit and Meta AI integration

**Important:** This is a wellness prototype, not a dehydration detector or medical device. Estimates are illustrative, not individualized medical advice. Avoid excessive fluid consumption.

## Run backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000/docs

## Run tests
```bash
python3 -m unittest discover -s tests -v
```

## iOS
Create a new Xcode iOS App project named `HydraAI` using SwiftUI, then add the Swift files from `ios/HydraAI`. The starter UI uses local demo data. It is not yet wired to the backend or HealthKit.

## Team workflow
Work on separate feature branches, open pull requests, and keep `main` stable. Never commit API keys, user health records, or `.env` files.
