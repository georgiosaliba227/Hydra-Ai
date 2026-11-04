# Compact Meta phone camera prototype

`dinov2-small-beverage-v1` freezes Meta's DINOv2 Small and fits a class-balanced
ridge head on the existing 150-photo training split. Validation chooses the
regularization from the fixed grid; the 75-photo test split is evaluated once
after selection. No personal photos or health data are used. See the source
manifest for public-image attribution and separate image/catalog licenses.

The fixed input is RGB224×224, full-image bilinear square resize, scale1/255
and internal ImageNet normalization. The Core ML graph uses the exactly
equivalent precomputed 224px position embedding because the converter does not
support the original dynamic bicubic-position operator. Three validation cases
check FP16 conversion parity (maximum score error below 0.007, same top class).
Core ML conversion warns that installed PyTorch 2.8 is newer than its tested 2.7;
numerical conversion and real runtime tests are required, not inferred from export.

The bundled package is 43,426,113 bytes. Its full file/source hashes, label order,
training configuration, parity and measured scores are in `reports/model-v1.json`.
Category top1: validation 16/25, test 50/75. Fixed minimum score 0.35 and margin 0.10
yield 57/75 test suggestions, 41 correct. These thresholds and the model were not
tuned on the test split. Scores are not probabilities; suggestions display low
confidence and require user review. This is not the earlier full-identity and
capacity benchmark. Open-world/non-beverage rejection and natural-glass coverage
are not established.

Use the isolated pinned development environment in `requirements-training.txt`.
The script never downloads or calls a provider. Supply a pinned local base with
`source.json` (model ID, exact revision and downloaded config/weight hashes), the
existing reviewed image root, and an output directory outside Git:

```sh
python scripts/train_on_device_beverage.py \
  --base /absolute/path/to/pinned-dinov2-small \
  --data-root /absolute/path/to/public-beverage-data \
  --manifest ai/beverage_training/manifests/beverage-250-20261102/manifest.jsonl \
  --output /absolute/path/to/export
```

Copy the verified `HydraBeverage.mlpackage` into `ios/HydraAI/Resources/` and
retain its model notice and Apache 2 license. Xcode compiles and bundles the model;
the app never downloads weights. Model identity, base revision, labels and input/
output dimensions are validated before local inference.
