# Beverage image adapter experiment

Owner assignment, November 2, 2026: collect approximately250 beverage images in varied real settings/backgrounds and train recognition of drink identity and volume, targeting measured success above70%. The owner selected actual open-Meta-model adapter training rather than calling prompt tuning weight training.

## Training and evaluation contract

Use an open Meta Muse Glimmer30B checkpoint in4-bit MLX form, pinning model and runtime revisions. Train low-rank language adapters with the image encoder/base weights frozen. Run on the owner's M4Pro24GB Mac; first verify a bounded forward/backward/update/save/reload cycle fits. No paid GPU or new hosted subscription is authorized. The existing Spark phone backend remains unchanged until this experiment has measured results.

Collect about250 unique licensed source photos, not generated backgrounds counted as real settings. Record sourceURL, sourceproduct/barcode, author, license, originalhash, processedhash, printed-capacity evidence, brand/product aliases (including preregistered brand_aliases for visible brand abbreviations) and reviewed background class. Exclude duplicate/near-duplicate views across splits. Group connected source-product IDs, near-duplicate groups and shared normalized full-identity aliases together, including the same visibly identifiable product under different barcodes or sizes. Source metadata is reference evidence, not guaranteed ground truth: check identity and printed quantity against the photo before admitting it. Separate studio/plain from natural backgrounds and report each stratum. Preregister at least100 natural-background photos overall, at least30 in the test split, and at least3 distinct reviewed natural test settings; a studio-only dataset cannot satisfy the request. Review `drink_family` using water/soda/juice/sports/energy/milk/plant_milk/tea/coffee/beer/wine/other. Require at least6 families with at least10 images each, no family over75 images, and at least5 test families with at least5 images each; many brands of one drink type cannot replace beverage diversity.

Volume means printed container capacity normalized to integer mL, not remaining liquid or consumption. Prefer the printed metric declaration over a fluid-ounce conversion; when printed metric mL is fractional, normalize with Decimal ROUND_HALF_UP to the nearest whole mL (502.8mL→503), retaining the literal decimal in capacity_evidence. Scoring requires the exact normalized integer, not a percentage tolerance. Visible label truth must be transcribed/verified independently of predictions. Serving quantity and multipack totals are not individual container capacity. An unreadable/unsupported quantity stays unknown; unknown capacity is not a successful positive volume prediction.

Freeze splits before training:150train,25validation,75test, adjusted only for indivisible product groups while preserving approximately250 total. Fit/choose adapters and decoding only on train/validation. Final test is scored after checkpoint selection; do not tune to it. If another iteration follows a failed final test, preserve its result and obtain fresh held-out examples rather than repeatedly optimizing against the same test.

Primary success requires BOTH correct top1 drink identity (brand plus product/type/flavor as visibly identifiable, under preregistered aliases) AND exact printed capacity mL on each eligible test case. Report identity, capacity, joint success, abstentions, errors, background strata, counts and95%Wilson intervals separately. Target is strictly>70% observed joint test success; do not claim population accuracy from a small sample or replace the metric with category-only accuracy. An easier proxy or synthetic replay cannot satisfy this goal.

Images/weights stay outside Git. Commit reproducible collection, validation, splitting, training, inference and scoring tools plus aggregate reports/manifests with attribution; no personal camera/HealthKit history is included. Inputs to the model contain pixels and the fixed recognition instruction only, never filenames, barcode metadata or ground-truth answers. Real updated adapter weights and before/after held-out predictions must exist before claiming training or success.

## Dependencies and source provenance

An isolated offline dataset-tools environment may use DuckDB (bounded Parquet projection/filtering) and Pillow (image decoding, duplicate checking and contact sheets); it does not change backend requirements. A separate Swift executable uses pinned official `ml-explore/mlx-swift-lm`, its MLX/tokenizer/download dependencies and the MLX-community4-bit conversion of the official Meta model. Record all resolved versions and licenses. Training images use their stated licenses/attribution; no arbitrary search-result scraping.

Primary references checked November2:
- https://dev.meta.ai/docs/muse-glimmer/post-training
- https://github.com/ml-explore/mlx-swift-lm
- https://huggingface.co/mlx-community/Muse-Glimmer-30B-4bit
- https://huggingface.co/datasets/openfoodfacts/product-database
- https://openfoodfacts.github.io/openfoodfacts-server/api/aws-images-dataset/
