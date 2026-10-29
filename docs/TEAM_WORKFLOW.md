# Team workflow

Track: **Startup**. Both named developers form the proposed team; confirm their individual eligibility and acceptance, and designate an authorized active-employee startup representative under the official rules. Planning PR #1 merged; the user reports both developers authorize cross-component implementation, with progress updates to Amine.

Proposed owners: `georgiosaliba227` iOS/camera/HealthKit/dashboard; `aminealichaouche` backend/Meta/calculations/database/integrations. Both approve architecture, integration, privacy, budget and submission.

Keep main stable. Start feature branches from current main, use pull requests and do not force-push. Agents may merge their own tested PRs under the AGENTS.md merge policy (2026-10-28). Proposed branch protection: require a peer review and relevant passing checks; repository settings/access have not been verified or changed. Collaborator access for both people still needs verification.

The six agent roles and path ownership are defined in root AGENTS.md. Architecture owns contracts; Documentation excludes `docs/architecture/`. The orchestrator integrates shared files. Use isolated worktrees and bounded tasks; no overlapping edits. Roles can run sequentially when concurrency is limited. This planning run launched two read-only research agents, not six implementation agents.

Before coding, approve contracts and assign issues. PR descriptions state behavior, evidence, test results and remaining limitations. No credentials, photos, personal health records, or raw sensitive prompts in commits/issues/CI. Budget status reports include settled plus reserved charges and reconciliation date, not sensitive account details.

Current GitHub CLI active identity is `georgiosaliba-lgtm`, not the requested owner; the owner exists as an inactive saved CLI account. Do not silently switch global accounts. Git transport read succeeded, but CLI repository metadata lookup failed with the active identity. Verify the intended account and both collaborators' access before publishing or configuring protection. Planning PR #1 was merged from `codex/planning-onboarding`; the saved owner account successfully created it without changing the global active account. Issue proposals remain local, and collaborator access still needs verification.
