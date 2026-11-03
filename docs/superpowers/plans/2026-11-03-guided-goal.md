# Guided goal implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the
> bounded model/store tasks and root inline integration.

**Goal:** Ask the requested profile questions and calculate a defensible,
explicitly confirmed adult beverage starting reference in the iPhone app.

**Architecture:** Pure calculator + protected local profile store + SwiftUI form;
reuse existing goal API and connection namespace. All profile fields stay local.

**Tech stack:** Existing Swift/Foundation/SwiftUI/XCTest, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-guided-goal-design.md` and
`docs/architecture/GUIDED_GOAL_POLICY.md`.

## Global constraints

- Healthy19+ adult beverage references3000/2200mL for explicit Men/Women rows.
- No body-size/supplement/creatine/heat/exercise numerical adjustment.
- Excluded/unknown applicability returns no reference; custom goal remains.
- No profile upload, new Health permission, automatic goal mutation or Meta call.
- Canonical data preserved; only confirmed goal integer goes to existing settings.
- Protected connection-scoped storage, explicit consent/export/delete, no real seeding.

## Review focus

- A nineteenth birthday and timezone transition cannot produce a premature adult row.
- Total-water references must never become beverage targets.
- Invalid optional data must not silently become a valid measured zero.
- Connection switches/canceled requests cannot apply another profile or goal.
- Corrupt/protected files must not be overwritten as an empty new profile.

### Task 1: Profile model and reference calculator

Files: new `ios/HydraAI/Data/GoalProfile.swift`,
`ios/HydraAI/Data/GoalReference.swift`, `ios/HydraAITests/GoalReferenceTests.swift`.

Interfaces: `GoalProfile: Codable, Equatable` fields/policy enums as contract;
`GoalReferenceCalculator.evaluate(_ profile: GoalProfile, now: Date = .now,
calendar: Calendar = .current) -> GoalReferenceResult`;
`GoalProfileValidation.validate(_:now:calendar:) throws`;
`GoalReferenceResult.reference(GoalStartingReference)` or `.unavailable(reason)`.
Reference exposes `beverageMl: Int`, `totalWaterMl: Int`, `ageYears: Int`,
`methodVersion`, `sourceURL`; reason provides readable text. Notify exact API early.

- [x] Write failing assertions for all adult bands3000/2200,19th birthday before/
  on/after, leap/future/impossible date, age-only/both-method conflict, unsupported
  eligibility and missing group, invalid/nonfinite measurements, and invariance
  under supported height/weight/supplement changes.
- [x] Run selected tests RED, implement versioned table lookup and validation,
  no optional-context coefficient or Meta/provider path.
- [x] Run focused GREEN, self-review, commit owned files and report for task review.

### Task 2: Protected local profile store

Files: new `ios/HydraAI/Data/GoalProfileStore.swift`,
`ios/HydraAITests/GoalProfileStoreTests.swift`. No view/BeverageStore edits.

Interfaces: MainActor observable store with profile/error/canSave; initializer
accepts directory + scopeResolver + injectable clock as needed;
`configure(_ configuration: APIConfiguration, now: Date = .now)`,
`reload(now:) throws`, `save(_ profile: GoalProfile, consent: Bool, now:) throws`,
`deleteCurrent() throws`, `deleteAll() throws`, `exportData(now:) throws -> Data`.
Uses Task1 validation and existing `CalibrationConnectionScope.resolve`.

- [x] Write failing tests for explicit consent, restart/scope switch/return,
  offline/invalid config, corrupt/oversized/symlink/wrong-scope schema preserving
  evidence, profile-only export, selective/all deletion, and privacy attributes.
- [x] Implement separate versioned envelopes, complete protection/atomic writes,
  backup exclusion and fail-closed save behavior; do not log contents.
- [x] Run focused GREEN after Task1 API integration, commit owned files and report.

### Task 3: Guided UI and existing goal integration

Root owns `BeverageStore.swift`, `BackendSettingsView.swift`, Home goal entry,
new `Features/Settings/GuidedGoalSetupView.swift`, any presentation helpers, UI tests,
HTTP/privacy tests and shared docs. New pure/store tasks do not edit these files.

- [x] Add UI RED for new guided entry/profile prompts with synthetic data only.
- [x] Integrate local store lifecycle with connection changes; add age/birthday,
  reference/applicability, optional ft/in/weight/supplement fields, source review,
  explicit confirmation and custom alternative. Implement local export/delete.
- [x] Capture candidate/connection generation at submission; preserve profile on
  network failure, ignore stale replies, update backend only through existing goal API.
- [x] Verify exact outgoing JSON has only daily_beverage_goal_ml; cancellation,
  failure and deletion; run full native/pytest plus actual Simulator guided flow,
  US/metric/profile persistence and older goal/score regression checks.
- [x] Obtain independent whole-branch review and fix/reverify findings.
- [x] Build/install the HealthKit-signed original app without reset.
- [ ] Complete owner-assisted guided confirmation on the phone (status only).
- [x] Publish final verification/docs and PR #77 stacked on #76, Amine requested. No merge.
