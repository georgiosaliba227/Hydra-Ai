# Frozen vision release patch

This patch modifies the official ml-explore/mlx-swift-lm runtime at the exact revision recorded in provenance.json. The upstream MIT notice is retained in UPSTREAM-LICENSE. The patch remains opt-in; Hydra enables it only for its local, frozen-vision recognition/training runner.

Use ../apply_runtime_patch.py after resolving Package.resolved and before building. The helper checks the upstream commit, complete tracked/untracked source state, patch digest and original/patched file digests, and refuses mixed or unexpected bytes. It does not alter the pretrained model, spending ledger, provider configuration or OS memory limits.

The runtime materializes image-conditioned embeddings before releasing on-demand vision and its free buffers. The source is retained so the next photo reloads the same frozen checkpoint. Attached vision is rejected when this policy is enabled. The official runtime revision, exact patch SHA, enabled policy and executable SHA are retained separately in inference evidence.
