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

- [ ] Restored goal core and protected local profile scope.
- [ ] Guided setup and saved-goal circle verified.
- [ ] One-button local analysis verified.
- [ ] Backend contract and feature routing verified with synthetic data.
- [ ] Complete checks/review, signed install and truthful physical handoff.
