# Rewarding Today progress — local verification

Environment: iPhone 17 Pro simulator, iOS 26.5, Xcode 27.2. All records and goals used here are synthetic local demo data. No provider calls, budget-ledger changes or deployment.

## Implemented

- Liquid gradient gauge, short settling wave, save pulse and ripple/sparkles.
- Four quarter-goal milestone bars and a distinct completed state.
- Press feedback and a saved receipt for drink shortcuts; shared durable acknowledgement feedback for confirmed drink creation.
- Optional persisted offline goals, accurate totals above the goal, and fill capped at 100%.
- Static Reduce Motion presentation, large-text layout, accessible totals and goal descriptions.

Feedback is an in-memory event after durable creation acknowledgement. Loading, refresh, goal changes, pending/failed saves and a late response from an old destination do not create a new celebration. No target, points or streak penalties are invented.

## Verification

- Full iOS unit suite: 86 passed. Includes offline goal persistence and amounts, acknowledgement/retry behavior and a controlled destination-change race.
- Standard offline UI flow: chosen 1,000 mL test goal; 250 mL → 25%, 750 mL → 75%, 1,000 mL → completed; state preserved after relaunch.
- Real simulator Reduce Motion setting in dark appearance: saving, numeric total, goal completion and visible accessibility checks.
- Maximum accessibility text size: stacked header and progress, readable volume, clipping/contrast checks, and manual logging remains reachable.
- Simulator video frames were inspected to confirm the liquid level moves, the wave/ripple runs and the animation settles. Physical haptic feel is unverified.
- Read-only review found two issues, both corrected: the pulse trigger stays stable when Reduce Motion changes, and the reduced-motion test establishes its own goal.

The native audit misreports the hidden amount captions inside quick-add buttons, even with white text at 14.66:1 contrast. Only these two uniform caption labels receive an independent rendered-pixel contrast check (minimum 4.5:1). Other visible contrast/clipping failures still fail. Offscreen/under-bar content and the existing system "nearly passed" notices are excluded from the focused audit.

Full pytest: 1,072 passed, 1 skipped, 32 subtests passed; one unchanged failure in `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]`. Its fixed 2026-10-30 sample is no longer in the future, so the route returns 409 rather than the expected 422. No Python source or tests changed. This remains a review PR; it is not merged.

## Captures

- [Quarter filled](../screenshots/rewarding-progress/quarter-filled.png)
- [Three quarters filled](../screenshots/rewarding-progress/three-quarters-filled.png)
- [Goal reached](../screenshots/rewarding-progress/goal-reached.png)
- [Dark / Reduce Motion](../screenshots/rewarding-progress/dark.png)
- [Maximum accessibility text](../screenshots/rewarding-progress/largest-text.png)

This verifies the local Today UI and mock accounting, not physiology, physical camera/HealthKit behavior, live AI, or the feel of haptics on an iPhone.
