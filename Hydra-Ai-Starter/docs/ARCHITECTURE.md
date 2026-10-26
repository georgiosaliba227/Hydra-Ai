# Architecture

SwiftUI iOS client → FastAPI `/forecast` → transparent estimation module.

Future integrations: Apple HealthKit (on-device permissions), weather provider, Meta model API for natural-language explanations. The AI model must not invent physiological measurements or claim to diagnose dehydration.

No health records should be sent to a third-party model without explicit user permission. Store minimal data and avoid logging sensitive payloads.
