# Rewarding progress implementation plan

**Goal:** Make confirmed drink logging feel satisfying and deliver simulator screenshots.

**Spec:** `docs/superpowers/specs/2026-11-03-rewarding-progress.md`

**Architecture:** A focused SwiftUI `TodayProgressCard` owns presentation and finite feedback. `BeverageStore.lastConfirmedBeverage` supplies an in-memory event only after durable acknowledgement. Existing summaries remain authoritative.

**Constraints:** No new dependencies, arbitrary targets, provider calls, or deployment. Preserve accounting and pending-request behavior. Keep work on the existing isolated feature branch and update its open review PR.

## Task 1: Confirmed feedback and visual progress

- [x] Extend the offline UI regression to require quarter-goal markers, capture partial and complete states, and verify relaunch persistence; run it against the old UI and confirm the missing markers fail.
- [x] Add unit assertions for confirmation-only feedback, failed-save/retry behavior, and no event replay after refresh/restart.
- [x] Add `BeverageStore.lastConfirmedBeverage: BeverageLog?`, clear on reconfiguration, publish after create acknowledgement and refresh.
- [x] Extract the progress view into `Features/Dashboard/TodayProgressCard.swift`. Build a liquid gauge, milestone rail, completion treatment, and finite pulse/ripple/particles. Keep accessible identifiers and user-goal semantics.
- [x] Give quick-add buttons press feedback and a saved receipt; use the shared confirmation event for haptics to avoid double feedback.
- [x] Run the full iOS unit suite and simulator UI regression. Inspect screenshots for partial and complete states, dark appearance and large text. Check Reduce Motion behavior.
- [x] Run pytest and report any unrelated baseline failures separately. Review the diff, document behavior, commit, push, and update PR #74 with screenshots and verification results.

## Review focus

Failed or pending saves must not celebrate; loading, navigation, and goal edits must not replay feedback. Over-goal totals remain accurate while fill caps at 100%. Reduce Motion must have no decorative movement. Large text must wrap without hiding logging controls. Any unchanged Python failure remains explicit in the verification report.
