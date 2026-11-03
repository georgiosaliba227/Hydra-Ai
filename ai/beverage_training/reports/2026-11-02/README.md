# Beverage adapter experiment — development results

The trained adapter has not yet met the held-out success goal. The first 75-photo test is now running after checkpoint/configuration selection was frozen. The results below are from the 25-photo development validation split and cannot establish final test accuracy.

The frozen dataset contains 250 distinct licensed photos in 227 connected product groups: 150 train, 25 validation and 75 test. It includes 120 natural-background photos and 12 beverage families. The test split contains 46 natural-background photos across seven settings. References, product grouping, labels and splits were frozen before predictions; see the attributed manifest in `../../manifests/beverage-250-20261102/`.

The owner approved equivalent full drink identities while retaining exact printed capacity. Two fresh, independently instructed Codex agents inspect anonymized identity-only packets; both must accept the complete identity. Uncertainty and disagreement fail. Printed capacity is scored deterministically in integer mL, with metric declarations preferred. Every case stays in the denominator.

| Same 1024-token pipeline | Full identity | Exact printed capacity | Both correct |
|---|---:|---:|---:|
| Unadapted Meta base | 19/25 (76%) | 22/25 (88%) | 18/25 (72%) |
| Trained adapter, two epochs | 18/25 (72%) | 23/25 (92%) | 17/25 (68%) |
| Selected trained adapter, one epoch | 18/25 (72%) | 24/25 (96%) | 18/25 (72%) |

Each pair of identity reviewers agreed on all 25 cases. The 95% Wilson interval for joint validation success is 52.4–85.7% for the base and selected one-epoch adapter, and 48.4–82.8% for the two-epoch adapter. Small validation counts do not establish population performance or an improvement over the base. One epoch was selected using validation only. Both final configurations were frozen at 2026-11-03T06:57:03.710647+00:00, before any test image entered the model; their selection records bind the immutable identity policy and exact model/configuration fingerprints.

The two-epoch run performed 300 actual updates on all 150 train photos: eight language layers, rank16 q/v LoRA, 2,260,992 trainable parameters, learning rate0.00003, nonzero parameter delta L2=3.230902916517203 and exact save/reload agreement. Adapter SHA256: `35e64c31a918a21a6b68e8e71c8c03c662b90786f15ba25e36726064909754e3`. Recorded wall time includes owner-requested pauses and is not a compute-only duration.

The selected one-epoch run performed 150 updates with the same settings, identical initial parameter tensors and exactly matching losses for the first 150 steps. Its parameter delta L2 is 2.883914224935822 and save/reload error is zero; wall time was 1,912 seconds without an owner pause. Selected adapter SHA256: `71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f`. This is real weight training with an earlier stopping point, not a renamed base model.

Training uses local Muse Glimmer30B 4-bit on the owner's Mac with frozen base/vision weights and detached-prefix response-only gradients. It does not train hosted Muse Spark weights. Photos, cached features and model checkpoints remain outside Git; no hosted inference, paid compute, phone deployment or financial-ledger changes were used for this experiment. The sampled 19GiB MLX and 20GiB RSS stop guards remain active.

The earlier 512-token experiment's literal-name comparison declined from 8/25 to5/25 joint; those failed results remain preserved. Legacy literal-name scores remain separate from the owner-approved full-identity criterion. Only the complete final-test provenance and dual-review evaluator may declare the current goal achieved.

Evidence here includes `adapter-train-v2-1024-e2.json`, both validation prediction files, both `*-equivalence.json` reports, the four independent review records and the immutable identity policy. The experiment contract and runtime instructions describe reproduction and the limits of hash-based provenance. Source verification after the final review passed 1,281 Python tests (5 skipped), plus the focused runtime/evaluation checks; the existing FastAPI/httpx deprecation warning remains.
