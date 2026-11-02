# Local Meta image adapter runner

This isolated macOS executable runs the pinned open Meta Muse Glimmer vision model. It never calls a hosted model or changes the phone/backend/provider spending records. Keep downloaded weights, photos and generated checkpoints outside Git.

## Build and unit checks

Swift 6.2 or newer, macOS 14 or newer, Xcode and the Metal Toolchain are required. The free official component can be installed with `xcodebuild -downloadComponent MetalToolchain` when `xcrun metal --version` reports it missing.

```sh
swift test -c release --jobs 4 --package-path ai/beverage_training/MetaAdapter --scratch-path /private/tmp/hydra-beverage-meta-build
python3 ai/beverage_training/MetaAdapter/Tests/test_launcher.py
```

Use the executable path printed by `swift build -c release --show-bin-path --package-path ai/beverage_training/MetaAdapter --scratch-path /private/tmp/hydra-beverage-meta-build`; SwiftPM's Xcode build system can place it under `out/Products/Release` instead of `release`. Pass that path with `--binary` if necessary.

The tiny random Muse architecture test checks that changing image pixels changes response logits, that response loss changes adapter parameters, and that saving/reloading preserves logits. It is a software fixture, not evidence about the real 30B model's fit or accuracy.

## Commands

The Python launcher validates the frozen manifest/policy and writes evaluator provenance. Use a fresh output directory for every invocation:

```sh
python3 scripts/train_meta_beverage_adapter.py smoke \
  --model /absolute/path/to/Muse-Glimmer-30B-4bit \
  --data-root /absolute/path/to/dataset \
  --manifest /absolute/path/to/reviewed-train-preflight.jsonl \
  --split-policy /absolute/path/to/preflight-policy.json \
  --output /absolute/path/to/artifacts/smoke-001 \
  --artifact-root /absolute/path/to/artifacts --image-tokens 128 --steps 1
```

`smoke` accepts a small reviewed train-only manifest, reports `beverage-preflight-v1`, and cannot satisfy the benchmark. `train` requires the complete reviewed experiment manifest, takes only train rows into the model process, and accepts a checkpoint as complete only after every train image has contributed an update. Defaults: one epoch, last one language layer, q/v projection LoRA, rank 4, scale 8, Adam learning rate 0.0001, zero dropout, seed 42.

Every model job requires `MODEL_DIR/base-provenance.json` from the reviewed downloader, schema `meta-base-provenance-v1`, binding the exact repository/revision and every downloaded file's size, SHA256 and provider LFS/content Git blob digest. The launcher verifies actual bytes, required model/tokenizer/processor files, all indexed weight shards and absence of symlink/traversal paths. An incomplete or mismatched base refuses to run. The runtime checks the proof file fingerprint again before loading; exact proof bytes are copied into each run artifact.

`infer --split validation` runs the fixed recognition instruction and pixels only; the child receives a label-free manifest projection. `--adapter /checkpoint/directory` enables the saved adapter. Final `infer --split test` additionally requires `--selection /selection.json` binding `selected_using: train_validation_only`, adapter SHA (null for baseline), split-policy SHA, `adapter_config_sha256`, `inference_config_sha256` and `checkpoint_frozen_utc`; the final adapter selection also lists the actual validation image IDs. Final test inference starts after that timestamp. Baseline and adapter have separate selection records because they bind different adapter hashes. Copy the canonical inference-config fingerprint from the actual validation run. It binds the exact binary, base proof, prompt, runtime, fixed header/date/reasoning and image/prefill/output/greedy and memory-budget settings; changing these after selection refuses final test admission.

Image tokens are bounded to 16–512, output/answer tokens to 16–192, prefill chunks to 1–128. Initial defaults are 128 image tokens and 96 answer/output tokens. More image resolution is useful for printed labels; choose resolution using train/validation before final test. MLX's `memoryLimit` is advisory: its allocator can exceed it. The runner checks a sampled MLX active-plus-cache budget (19 GiB maximum) and resident-process budget (20 GiB default/maximum), checks each completed model phase, and samples every 50 ms during work. The launcher independently samples child RSS with macOS `libproc` and terminates an over-budget process. A 64 MiB reusable buffer cache limits retained free buffers. These are sampled stop guards, **not a hard allocation cap**: a single allocation may overshoot before the next observation. Recoverable MLX backend errors become Swift throws; GPU-driver aborts remain subprocess failures. Failed jobs preserve a sanitized `failure.json` and cannot produce an accepted training result. No OS wired-memory limit is changed. A process lock permits one local model job at a time. Each phase prints aggregate MLX active/cache/peak bytes and process peak RSS. A hardware preflight must measure the real checkpoint before a fit claim.

## Actual training method and limits

The image encoder and base model remain frozen. Each sample builds fresh image-conditioned KV caches for all but the final prompt token outside the gradient trace. The loss runs on the final prompt token followed by teacher-forced response tokens, with targets covering every answer token, including the first token and end marker. Only response positions contribute loss. Gradients flow through the last language layer's q/v adapters and attention to the visual prefix; they do **not** flow through image encoding or earlier prompt KV computation. This is a detached-prefix approximation to full multimodal fine tuning and is recorded as `image-conditioned-detached-prefix-response-only-lora` in `training.json`.

The released ATEM template ends with an assistant prefix. Both training and inference append the fixed ` to=user<|message|>` header, set low reasoning strength and fix the template date to 2026-11-02. No filename, barcode, source-product metadata or label enters model input. Printed capacity is a positive integer mL value or null. Raw model generations and photo contents are never logged; failed output validation becomes an error prediction and remains a scoring failure.

A completed training artifact contains `initial-adapters.safetensors`, `adapters.safetensors`, `adapter_config.json`, `training.json`, `runtime.json`, exact `prompt.txt`, copied `model-provenance.json`, and `inference-config.json`. Evidence includes nonzero optimizer steps/parameter delta, different initial/final adapter hashes, tensor save/reload error, full train-manifest SHA, actual train image IDs, loss history and memory telemetry. Smoke also compares model logits after reloading. These checks do not establish recognition accuracy; the separate blind evaluator measures that.

## Pinned dependency need and provenance

- Official `ml-explore/mlx-swift-lm` revision `b8d4935ab152169ac8cb0da5414b51447e78efb1` (MIT): Muse Glimmer architecture, image processor, cache handling and LoRA modules.
- Official `ml-explore/mlx-swift` 0.33.0 (MIT): Apple GPU tensors, automatic differentiation, optimizer and tensor checkpoint IO. Its source pins C++ MLX `36969c094354086e15d2a327a9c50feb20b9cf11` and mlx-c `a26f2d584a14ec619ae8db9a09be03becd47598a`.
- Hugging Face `swift-transformers` 1.3.0 revision `b38443e44d93eca770f2eb68e2a4d0fa100f9aa2` (Apache-2.0): offline tokenizer and released Jinja chat-template support. The runner supplies an explicit local tokenizer bridge, so it does not invoke a downloader or load credentials.
- `Package.resolved` records all transitive resolved revisions. These dependencies are isolated from backend and iPhone requirements.
- Base checkpoint: `mlx-community/Muse-Glimmer-30B-4bit`, Hugging Face revision `3e7677d7a40d348a3daba263a2b1c0aa41910710`; follow the checkpoint's Meta Muse model license. The reviewed downloader creates provider evidence; the launcher verifies the downloaded bytes before the executable loads them.

No full-model fit, training completion or recognition success is claimed by the source package alone.
