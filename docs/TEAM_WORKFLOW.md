# Team workflow

Proposed owners: `georgiosaliba227` iOS/camera/HealthKit/dashboard; `aminealichaouche` backend/Meta/calculations/database/integrations. Both approve architecture, integration, privacy, budget and submission.

Keep main stable. Start feature branches from current main, use reviewed pull requests and do not force-push or automatically merge. Proposed branch protection: require a peer review and relevant passing checks; repository settings/access have not been verified or changed. Collaborator access for both people still needs verification.

The six agent roles and path ownership are defined in root AGENTS.md. Architecture owns contracts; Documentation excludes `docs/architecture/`. The orchestrator integrates shared files. Use isolated worktrees and bounded tasks; no overlapping edits. Roles can run sequentially when concurrency is limited. This planning run launched two read-only research agents, not six implementation agents.

Before coding, approve contracts and assign issues. PR descriptions state behavior, evidence, test results and remaining limitations. No credentials, photos, personal health records, or raw sensitive prompts in commits/issues/CI. Budget status reports include settled plus reserved charges and reconciliation date, not sensitive account details.

Current GitHub CLI active identity is `georgiosaliba-lgtm`, not the requested owner; the owner exists as an inactive saved CLI account. Do not silently switch global accounts. Git transport read succeeded, but CLI repository metadata lookup failed with the active identity. Verify the intended account and both collaborators' access before publishing or configuring protection. No issues, PRs, notifications, or remote writes were made in this planning run; issue proposals are local.
