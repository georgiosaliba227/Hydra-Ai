# Frozen public beverage-photo cohort

This is the preregistered 250-photo cohort for local Meta adapter training. It contains references and independently reviewed labels, not image files, user camera photos, health data, model weights or provider credentials. Training/validation/test counts are 150/25/75. No recognition accuracy is established by this dataset.

Each manifest row attributes the source image URL, contributing author, original/processed hashes, visible printed-capacity evidence and license. Images are Open Food Facts contributor photos under CC-BY-SA-3.0: https://creativecommons.org/licenses/by-sa/3.0/. Preserve contributor attribution and the image license when redistributing photos. Source database metadata is Open Food Facts under ODbL-1.0: https://opendatacommons.org/licenses/odbl/1-0/. These dataset terms are separate from the code license.

The complete source catalog was verified against the publisher LFS SHA256 before freezing; source-provider.json retains its pinned revision and provider digest, and source-verification.json retains the actual verified bytes/hash. Public image content is independently bound by each row's original and normalized SHA256. Source metadata is not the reference answer: visible labels were reviewed before model predictions and often corrected catalog quantities.

Use the explicit external data root containing images/ when invoking the training/evaluation tools. Image normalization is EXIF orientation correction, RGB conversion, maximum 1600x1600 thumbnail and JPEG quality94 without EXIF, using Pillow13.0.0. Raw originals, processed images and review contact sheets remain outside Git.

Product IDs, shared normalized full-identity aliases and near-duplicate dHash groups are closed together before assigning splits, including different barcodes/sizes. The hardware-preflight photo is reserved for train. Test references and assignments must not change after checkpoint selection. See docs/architecture/BEVERAGE_ADAPTER_TRAINING.md for the exact scoring and experiment contract.
