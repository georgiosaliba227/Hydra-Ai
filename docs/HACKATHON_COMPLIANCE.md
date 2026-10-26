# Startup hackathon compliance register

Updated 2026-10-26. **Hydra AI is entering the Startup track**, as confirmed by the user. Official rules are now readable through the browser; this supersedes the earlier inaccessible-rules finding. Reading them did not accept terms, register participants or submit a project.

## Official rules and team eligibility

The [Official Rules and Event Waiver](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver), sections “Event Overview” and “Age Restrictions and Eligibility Requirements”, allow Startup participation for technical founders building a product. Teams appoint a representative authorized to submit for them; the Startup representative must be an active employee of the startup and authorized to receive notices/prize payment. Every member must read and agree to the rules; participants and projects enter only one track.

**Two developers can form the proposed Startup team, subject to these conditions. Neither developer's personal eligibility or acceptance is independently confirmed.** The Startup provision does not state a numeric team-size limit; do not import another track's limit or treat its absence as unconditional eligibility.

| Human verification | georgiosaliba227 | aminealichaouche |
|---|---|---|
| Applied and accepted through the official process | Pending | Pending |
| At least 18 and local age of majority | Pending | Pending |
| Meets residence, sanctions, employment/affiliation and family/household exclusions | Pending | Pending |
| Read/agreed to rules; participates in this single Startup track | Pending | Pending |
| Startup technical-founder/product status and team membership established | Pending | Pending |

The team must also identify which person is its authorized active-employee representative. GitHub identity and a credit balance do not prove these requirements. Obtain organizer clarification if founder/employee status or track registration is uncertain; no organizer contact has been sent.

## Verified project judging and submission requirements

The rules' project rubric (distinct from application screening) is:

| Criterion | Weight |
|---|---:|
| Impact | 30% |
| Use of Meta AI Tooling | 25% |
| Technical Depth & Execution | 20% |
| Demo | 25% |

The rubric assesses real-world usefulness, meaningful Meta integration, engineering quality, a working live demonstration and demo-video quality. It applies to hackathon projects; no separate weighted Startup rubric was found. The [official event page](https://dev.meta.ai/events/global-hackathon) additionally emphasizes technical execution and production readiness for Startup projects.

Submit via the [official submission portal](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit) through the authorized representative. The event page gives **November 4, 2026, 9 PM ET** as the deadline, subject to updates. The portal showed public event information in the unauthenticated browser, not a submission form; required fields, video length, repository/deployment access and upload formats still require participant-side verification.

The rules require original work and appropriate rights; open-source components are allowed with license compliance and added work. Entrants retain ownership but grant broad enduring usage rights to organizers; review the “Hackathon Submission” and “Release of Information” sections before submission. Third-party technical assistance is permitted under ownership conditions, but Codex-specific permission and treatment of pre-existing starter work were not explicit. Confirm those details rather than assume them.

## Credits and billing

User-confirmed dashboard snapshot, 2026-10-26: **$150.00 free Meta Model API credits**, **$0.00 pay-as-you-go balance**, **payment method attached**. This is one shared project allocation, not per developer. The agent has not independently inspected the dashboard. Official rules describe a 10-day development credit window and link Credit Terms; exact account expiry, eligible usage, redemption/coverage and overage terms still require verification. No other participant or partner credit expands this project's ceiling.

Meta's [billing help](https://dev.meta.ai/help/billing/spend-limit-alert) confirms email alerts rather than a hard cap and liability for excess usage. Free credits and a zero payable balance do not eliminate overage risk or prove zero cumulative usage. Maintain the **$120 gross cumulative-usage cutoff and $30 reserve**, $75 notification and $100 approval gate. Require one persistent, centralized, fail-closed controller with atomic reservations; it is not implemented yet. No automatic top-ups, uncontrolled calls or paid requests are authorized.

## Remaining approval checklist

- [ ] Both developers verify the individual and Startup team conditions above and choose the representative.
- [ ] Verify participant portal submission fields, model eligibility details, coding-assistant/pre-existing-code treatment and licensing obligations.
- [ ] Verify exact credit expiry/coverage, historical gross usage and cash-overage behavior against the account and linked Credit Terms.
- [ ] Implement/test the controller only in the approved later phase; verify concurrency, retries, recovery, all spending paths and reconciliation before separate paid-call approval.
- [ ] Review and approve planning PR #1 before beginning Milestone 1. No automatic merge.
