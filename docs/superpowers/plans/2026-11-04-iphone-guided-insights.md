# Guided setup and insights integration plan

Spec: `docs/superpowers/specs/2026-11-04-iphone-guided-insights-design.md`.
Worktree is already isolated; branch `codex/iphone-guided-insights` starts at the
verified offline-camera/water-fill build. Preserve all existing records and the
running owner backend while preparing a reviewable nonbillable integration.

1. Restore prior goal/profile/reference/unit modules and tests in an isolated
   bounded subtask. Add a stable local destination while preserving old scopes.
2. Integrate guided goal setup into first use, Today and Settings; serialize goal
   changes and keep the existing water fill driven by the confirmed saved goal.
3. Observe a one-button local analysis UI regression fail, remove the local-only
   checkbox, and verify real model review/save/stale-source behavior.
4. Define the ephemeral device-insights contract; implement backend validation
   and separate client connection/routing without moving local records.
5. Exercise Trends, Ask Hydra and workout paths through a synthetic nonbillable
   backend. Verify real owner connection safely, without personal-data API probes
   or paid requests. Review, run suites, build/sign and install in place.

- [x] Restored goal core and protected local profile scope; 41 focused and 170 native tests in isolated subtask.
- [x] Research individualized goal methods, including 2026 evidence; no validated daily beverage target established. Owner then chose a clearly labelled, confirmed adult starting reference during further research.
- [x] Integrate confirmed interim reference into first use, Today and Settings; first-use review, profile persistence, under-19 abstention/custom path and adopted-goal water progress verified in synthetic UI tests.
- [x] One-button local analysis verified; expected checkbox regression RED, four real-model/progress UI tests GREEN.
- [x] Backend contract and separate feature routing verified with synthetic phone data; Trends, contextual Ask, workout and restart flow passed. Owner features-only backend authenticated with no personal-data probe.
- [x] Review and checks complete: 1457 pytest passed (5 optional skips, 58 subtests), 202 native XCTest passed, 7 relevant UI flows passed; strict signed/profile checks passed.
- [x] Signed update installed successfully in place over Wi-Fi after owner unlocked both devices.
- [x] Owner confirmed “Backend features connected” on the physical phone. Screen sharing stopped; owner chooses profile/source and confirms the goal in guided setup. Review handoff records the blocked GitHub PR permissions separately.
