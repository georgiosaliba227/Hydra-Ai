# Animated Hydra UI

User request: make the iPhone interface animated and fun, and replace the camera's developer-facing workflow with capture, a scanning-bottle animation, and displayed beverage data.

Implementation choice: native SwiftUI, aqua/ink/lime palette, rounded cards, floating bottle artwork and a moving scan beam. Refresh Today, the volume hero and camera; retain existing tab destinations. Respect Reduce Motion, Dynamic Type and light/dark appearance.

Approaches considered: cosmetic reskin alone leaves camera friction; fully automatic upload removes the required per-photo consent. Use a camera-focused screen with a compact per-photo sharing sheet and one explicit Scan photo action instead. No provider jargon in primary actions. Identify Meta and retention in the sharing disclosure, and clearly label mock responses as demonstrations. Export and test controls remain in Camera options.

The scanner reflects an actual pending request; no invented progress percentages or artificial success. Display candidate identity, capacity, confidence, sourced nutrients and unknown states. Existing confirmation remains required before logging consumed volume. No API changes, new dependencies, paid calls, private ledger changes or deployment.

Integration: built on latest main 3f258ce, preserving Insights, quick-add drinks, guided workout/health/weather features and shared components. Motion lives in HydraMotion.swift alongside the existing HydraStyle.swift.
