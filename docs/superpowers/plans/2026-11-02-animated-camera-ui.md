# Animated Hydra UI Implementation Plan

**Goal:** A playful native dashboard and capture → consent → scan → results camera flow.
**Architecture:** Reuse CameraSession request tickets and HTTPBeverageService. Presentation components own animation, session owns scoped consent. Existing confirmation owns writes.
**Tech Stack:** SwiftUI, XCTest, existing FastAPI test fixtures.
**Spec:** docs/superpowers/specs/2026-11-02-animated-camera-ui-design.md

## Constraints and review focus
- No provider requests in verification; local fake provider only.
- Consent must not survive photo/configuration/mode changes; stale responses stay rejected.
- No invented nutrients, capacities, progress or automatic logging.
- Reduce Motion disables decorative motion; content must remain accessible at larger text sizes.
- Missing camera, offline backend, ambiguous results and failures retain manual entry.

## Tasks
- [x] Add scoped scan-consent tests in CameraSessionTests; observe failure, implement grant method and verify.
- [x] Add reusable native theme, bottle and scan presentation components; refresh DashboardView, LoggedVolumeCard and RootView.
- [x] Simplify CameraCaptureView into capture, sharing sheet, pending scanner and candidate data cards; keep export/demo controls in options.
- [x] Adapt camera UI integration tests to the explicit sheet action. Verify cancel, fresh photo, refresh, duplicate candidates, logging and unchanged totals before confirmation.
- [x] Run all Swift unit tests, local fake-provider UI integration and pytest. Inspect simulator screenshots and review branch diff.
- Delivery: commit on the feature branch and open a review PR for Amine.

## Progress
Implemented in the managed worktree on codex/animated-camera-ui. Integrated latest main 3f258ce after discovering the initial local checkout was behind; preserved Insights, quick logging, user goals and the workout/health/weather additions.

Independent code review found no blocking issues. Its goal-discoverability and large-text observations were addressed. Accessibility testing led to a separate-line dashboard heading, an explicit History empty state, darker shared hint text and tint, and scan status outside the clipped artwork.

The latest main contained a time-dependent workout fixture whose "future" sample was fixed to October 30. The existing failing parameter now constructs its future date relative to UTC now; backend behavior is unchanged. Full pytest passes: 1,073 tests plus 32 subtests, one skip, one upstream dependency deprecation warning.

Swift unit suite: 85 passed. Focused simulator checks cover large-text camera navigation, manual persistence, mock confirmation, user goal progress, live-mode consent using a fake provider, and main-screen accessibility. Final accessibility audit passed across Today, Camera, History, Settings and Ask Hydra. The live-mode fake-provider case passed in light and dark appearance. Screenshots are in docs/screenshots/animated-ui/. No paid inference or physical-device validation.

The initial UI audit failures were corrected, including iOS 26 scroll-edge fading that reduced contrast above the tab bar. Test tolerances were not relaxed. A simulator launch failure was resolved by booting the dedicated test simulator before the run.
