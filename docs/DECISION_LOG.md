# Hydra AI decision log

Only current cross-component decisions belong here. Detailed contracts stay in docs/architecture/; historical review reports retain their original evidence.

| Date | Decision | Reason / authorization |
| --- | --- | --- |
| 2026-10-27 | Prioritize real Meta camera and synthetic hydration interpretation, reproducible evaluation, and the existing iPhone confirmation path; defer unrelated UI and speculative work | Latest user instruction authorizes parallel implementation/testing and GitHub coordination, but explicitly withholds billable requests, photo disclosure and automatic merges |
| 2026-10-27 | Continue from existing integration PR #13 on an isolated Meta-first review branch | #13 now exists at `be4e492`; preserve #9/#10/#11 and integration history. CLI comments work; owner connector writes return 403 |
| 2026-10-27 | Continue the authorized roadmap during the active execution, delegating non-overlapping work; retain four shared status files | User's autonomous development request; no claim of work after execution ends and no scheduled task requested |
| 2026-10-27 | Combine #10 (including human-merged #12), #11 and #9 on a new isolated integration branch | Test semantic compatibility without rewriting source branches or merging GitHub PRs |
| 2026-10-27 | The active first-test restriction remains one project-wide named-account/exact-image request <=$0.25; dual-test-v1 <=$2/account remains an unapproved, disabled proposal | Current explicit user instructions take precedence over proposal wording in branch docs. A changed policy requires a new explicit human decision, never inferred from code or silence |
| 2026-10-27 | Frozen account state blocks all project admission/send paths, including another account's existing permit | Anomalous first-attempt billing must not allow cross-account continuation |
| 2026-10-27 | Usage settlement and provider invoice finality are distinct; require explicit immutable reviewed finality before another request | New fail-closed contract in GUARDED_META_API.md; temporary synthetic tests only. No production evidence/migration or cost correction implied |
| 2026-10-27 | An actual workout observation is a completion timestamp and must allow its minimum measured duration to have elapsed | Reject impossible intervals using UTC time and explicit duration-error bounds; no new scientific formula |
| 2026-10-27 | First native forecast consumer is history-only, with unavailable daily requirements and no calibration or HealthKit upload | Existing deterministic endpoint can improve demo integration without new health disclosure or unsupported targets |
| 2026-10-27 | Preserve the permanent ledger unchanged; verify ownership, permissions, integrity and counts read-only | Existing schema initialization was documented in #12; empty records cannot authenticate historical provider spending |

Publication access: the branch push succeeded, but CLI PR creation and the connected owner app both lacked the required permission. The browser was signed out. Preserve the pushed branch and complete PR description on #10; do not alter credentials or access settings to resolve this.

No decision authorizes paid inference, support messages, deployment, credential changes, production migrations, purchases or automatic merges. GitHub coordination/review notifications are authorized by the user's request.
