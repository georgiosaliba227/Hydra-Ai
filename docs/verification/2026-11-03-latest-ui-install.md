# Newer UI installed on iPhone

The earlier crash repair was built from `codex/home-hydration-progress`, which did not contain the newer Home score, US-unit presentation, automatic-context UI, or guided goal setup. The user identified the visual mismatch.

The corrected installation uses the existing, clean `codex/guided-hydration-goal` checkout at `f9422462b50f86ff6d120564721750f148ef8179` (PR #77). That source already contains the portable `DateOrdering` compatibility fix. This installation did not modify its source, financial ledgers, or backend configuration.

## Verification performed

- Fresh signed Release device build: passed. Strict signature verification passed; the original bundle identity and HealthKit entitlement were checked. No weak imports of the problematic `Date >=`/`<=` entry points remain.
- Executable UUID: `8ABBF7F8-32E6-33FD-B485-AD3C92924F2D`.
- In-place physical iPhone installation: passed, using the same bundle identifier and signing team; no uninstall/reset.
- Normal foreground launch: passed. Process remained present after 22.5 seconds; a captured Today screen displays US fl oz and the Hydration score card with guided goal navigation.
- A second launch request succeeded. Its later process check was inconclusive after the phone left Hydra; it is not reported as a sustained-relaunch pass.
- Fresh signed iOS 27.0 simulator native unit suite: **254 tests passed, zero failures**.
- Personal screenshot returned privately to the user and retained outside Git. No synthetic drinks or profile answers were entered on the phone.

The older UI screenshot and build UUID in the prior launch-investigation report describe the earlier installation, which this newer build supersedes. PR #74 remains a separate review branch; this operation installed the already implemented UI from PR #77 and did not merge branches or enable inference.
