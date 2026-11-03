# Beverage adapter experiment — measured results

The locally trained Meta Muse Glimmer adapter met the observed held-out target: **63/75 (84%)** photos had both the full beverage identity and exact printed capacity correct. Exact capacity was correct on **73/75 (97.3%)**. All 75 cases remained in the denominator. The checkpoint and both inference configurations were selected using train/validation only and frozen before test encoding.

| Held-out 75-photo test, same 1024-token pipeline | Full identity | Exact printed capacity | Both correct |
|---|---:|---:|---:|
| Unadapted Meta base | 59/75 (78.7%) | 70/75 (93.3%) | 57/75 (76%) |
| Selected trained adapter, one epoch | 63/75 (84%) | 73/75 (97.3%) | 63/75 (84%) |

The adapter's joint result was 38/46 (82.6%) on natural backgrounds, 24/28 (85.7%) on plain backgrounds and 1/1 in the studio stratum. Compared with the base, nine cases improved and three regressed; 54 were correct under both and nine incorrect under both. These are observed paired counts, not a population or causal improvement claim.

The nominal per-photo 95% Wilson interval for joint success is 74.1–90.6% for the adapter and 65.2–84.2% for the base. These intervals do not adjust for product-group correlation or grader uncertainty. The two independent AI reviewers agreed on the adapter's exact verdict in 73/75 cases and on equivalence in 74/75; disagreement and uncertainty fail conservatively. All model outputs were schema-valid. Median language-worker latency was 14.19 seconds per photo (95th percentile 15.31 seconds), excluding separate vision encoding and initial model load.

The frozen dataset contains 250 distinct licensed photos in 227 connected product groups: 150 train, 25 validation and 75 test. It includes 120 natural-background photos and 12 beverage families. The test split contains 46 natural-background photos across seven settings. References, product grouping, labels and splits were frozen before predictions; see the attributed manifest in `../../manifests/beverage-250-20261102/`.

The owner approved equivalent full drink identities while retaining exact printed capacity. Two fresh, independently instructed Codex agents inspect anonymized identity-only packets; both must accept the complete identity. Uncertainty and disagreement fail. Printed capacity is scored deterministically in integer mL, with metric declarations preferred. Every case stays in the denominator.

| Development validation, same 1024-token pipeline | Full identity | Exact printed capacity | Both correct |
|---|---:|---:|---:|
| Unadapted Meta base | 19/25 (76%) | 22/25 (88%) | 18/25 (72%) |
| Trained adapter, two epochs | 18/25 (72%) | 23/25 (92%) | 17/25 (68%) |
| Selected trained adapter, one epoch | 18/25 (72%) | 24/25 (96%) | 18/25 (72%) |

Each pair of identity reviewers agreed on all 25 cases. The 95% Wilson interval for joint validation success is 52.4–85.7% for the base and selected one-epoch adapter, and 48.4–82.8% for the two-epoch adapter. Small validation counts do not establish population performance or an improvement over the base. One epoch was selected using validation only. Both final configurations were frozen at 2026-11-03T06:57:03.710647+00:00, before any test image entered the model; their selection records bind the immutable identity policy and exact model/configuration fingerprints.

The two-epoch run performed 300 actual updates on all 150 train photos: eight language layers, rank 16 q/v LoRA, 2,260,992 trainable parameters, learning rate 0.00003, nonzero parameter delta L2=3.230902916517203 and exact save/reload agreement. Adapter SHA256: `35e64c31a918a21a6b68e8e71c8c03c662b90786f15ba25e36726064909754e3`. Recorded wall time includes owner-requested pauses and is not a compute-only duration.

The selected one-epoch run performed 150 updates with the same settings, identical initial parameter tensors and exactly matching losses for the first 150 steps. Its parameter delta L2 is 2.883914224935822 and save/reload error is zero; wall time was 1,912 seconds without an owner pause. Selected adapter SHA256: `71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f`. This is real weight training with an earlier stopping point, not a renamed base model.

Training uses local Muse Glimmer 30B 4-bit on the owner's Mac with frozen base/vision weights and detached-prefix response-only gradients. It does not train hosted Muse Spark weights. Photos, cached features and model checkpoints remain outside Git; no hosted inference, paid compute, phone deployment or financial-ledger changes were used for this experiment. The sampled 19 GiB MLX and 20 GiB RSS stop guards remained active. All model jobs have exited.

The earlier 512-token experiment's literal-name comparison declined from 8/25 to5/25 joint; those failed results remain preserved. Legacy literal-name scores remain separate from the owner-approved full-identity criterion. Only the complete final-test provenance and dual-review evaluator may declare the current goal achieved.

The first held-out baseline review exposed a scorer bug: it rejected complete brand/name text placed entirely in one nullable field, although the frozen rubric allowed field partition. The implementation was corrected with failing-then-passing regression tests and a fresh source review. Raw judgments, labels, aliases, exact volume, policy, denominator and inference configuration remained unchanged; all three development results were regraded and remained identical. The implementation note preserves this history. No final score had been issued before that correction.

Evidence includes `final-comparison-v2-e1.json`, both `*-test-v2-1024-e1-equivalence.json` reports, all four held-out review records, all saved test predictions, training/update/reload evidence, frozen selections, the artifact index and immutable identity policy. Public photos may have appeared in base pretraining; the test set was held out from this adapter's training and selection. AI review is not a human population study, and hashes do not authenticate visual truth or reviewer independence. Source verification passed **1,284 Python tests, 5 skipped and 58 subtests**; the existing FastAPI/httpx deprecation warning remains. The current native binary previously passed 14 Swift tests and real-checkpoint preflights; no Swift changes followed those checks.

The source and results are pushed on `codex/beverage-adapter-training`. The prepared review description is in `docs/reviews/2026-11-03-beverage-adapter-pr.md`. PR creation was rejected by GitHub with HTTP403 `Resource not accessible by integration`; the owner can open the prepared branch comparison and request Amine's review. No merge or deployment has occurred.
