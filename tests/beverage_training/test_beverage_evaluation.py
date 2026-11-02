"""Offline fixtures exercise scoring; these are never measured photo results."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest

from ai.beverage_training import evaluation as ev


def sha(data):
    return hashlib.sha256(data).hexdigest()


def row(i, split="test", capacity=330):
    return dict(image_id=f"image-{i}", source_url=f"https://example.org/{i}.jpg",
        source_product_id=f"product-{i}", source_revision="2026-11-02", author="Photographer",
        license="CC-BY-SA-3.0", original_sha256=sha(f"original-{i}".encode()),
        image_sha256=sha(f"pixels-{i}".encode()), image_path=f"{i}.jpg", brand="ACME",
        product="Lime sparkling water", drink_family="water", identity_aliases=["Acme Lime sparkling water", "Acme Lime seltzer"],
        capacity_ml=capacity, capacity_visible=capacity is not None,
        capacity_evidence="Printed 330 mL" if capacity else "No readable capacity",
        background="natural", background_detail="outdoor table", reviewer="independent-human", review_status="reviewed", split=split)


def prediction(i, **changes):
    value = dict(image_id=f"image-{i}", model_id="meta/test", base_revision="a"*40,
        adapter_sha256=None, prompt_sha256="b"*64, outcome="success", brand="ACME",
        product="Lime sparkling water", capacity_ml=330, latency_ms=10, error=None)
    value.update(changes)
    return value


class ScoringTests(unittest.TestCase):
    def test_missing_failed_and_unknown_capacity_stay_in_joint_denominator(self):
        rows = [row(i) for i in range(5)]
        rows[4] = row(4, capacity=None)
        preds = [prediction(0), prediction(1, outcome="error", error="decode_failed"),
                 prediction(2, capacity_ml=331), prediction(4, capacity_ml=None)]
        report = ev.score_predictions(rows, preds)
        self.assertEqual(report["counts"], dict(total=5, received=4, missing=1, failed=1,
            valid=3, identity_correct=3, capacity_correct=1, joint_correct=1,
            abstained_identity=0, abstained_capacity=1, unsupported_capacity=0,
            known_capacity=4, unknown_capacity=1))
        self.assertEqual(report["joint"]["rate"], .2)
        self.assertEqual(report["capacity"]["rate"], .2)
        self.assertEqual(report["coverage"]["rate"], .6)
        self.assertEqual(report["backgrounds"]["natural"]["joint"]["correct"], 1)
        self.assertAlmostEqual(report["joint"]["wilson95"][0], .0362241, places=6)
        self.assertAlmostEqual(report["joint"]["wilson95"][1], .6244654, places=6)

    def test_top1_full_identity_normalizes_unicode_punctuation_but_not_category(self):
        rows = [row(i) for i in range(4)]
        preds = [prediction(0, brand="ＡＣＭＥ", product="LIME—seltzer"),
                 prediction(1, brand="", product="sparkling water"),
                 prediction(2, brand="Other", product="Lime sparkling water"),
                 prediction(3, product="Lime sparkling water cherry")]
        report = ev.score_predictions(rows, preds)
        self.assertEqual(report["identity"]["correct"], 1)
        self.assertEqual(report["capacity"]["correct"], 4)
        self.assertEqual(report["joint"]["correct"], 1)

    def test_threshold_is_strict_and_unknown_positive_is_unsupported(self):
        rows = [row(i) for i in range(10)]
        preds = [prediction(i, capacity_ml=330 if i < 7 else 500) for i in range(10)]
        self.assertFalse(ev.score_predictions(rows, preds)["above_70_percent"])
        preds[7]["capacity_ml"] = 330
        self.assertTrue(ev.score_predictions(rows, preds)["above_70_percent"])
        unknown = ev.score_predictions([row(0, capacity=None)], [prediction(0)])
        self.assertEqual(unknown["counts"]["unsupported_capacity"], 1)
        self.assertEqual(unknown["joint"]["correct"], 0)

    def test_duplicate_or_outside_split_prediction_is_rejected(self):
        for preds in ([prediction(0), prediction(0)], [prediction(99)]):
            with self.assertRaises(ValueError):
                ev.score_predictions([row(0)], preds)

    def test_family_strata_include_failures_without_changing_total(self):
        rows = [row(i) for i in range(3)]
        rows[2]["drink_family"] = "soda"
        report = ev.score_predictions(rows, [prediction(0), prediction(2, capacity_ml=500)])
        self.assertEqual(report["drink_families"]["water"]["joint"]["correct"], 1)
        self.assertEqual(report["drink_families"]["water"]["counts"]["missing"], 1)
        self.assertEqual(report["drink_families"]["soda"]["joint"]["correct"], 0)
        self.assertEqual(report["joint"]["total"], 3)

    def test_null_identity_is_abstention_with_independent_capacity_success(self):
        rows = [row(i) for i in range(4)]
        predictions = [prediction(0, brand=None), prediction(1, product=None),
            prediction(2, brand=None, product=None),
            prediction(3, brand=None, product="Acme Lime sparkling water")]
        report = ev.score_predictions(rows, predictions)
        self.assertEqual(report["counts"]["valid"], 4)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["capacity"]["correct"], 4)
        self.assertEqual(report["identity"]["correct"], 0)
        self.assertEqual(report["joint"]["correct"], 0)
        self.assertEqual(report["counts"]["abstained_identity"], 4)
        self.assertEqual(report["identity_abstention"]["rate"], 1.0)

    def test_invalid_identity_types_remain_failed_and_blank_component_abstains(self):
        for field in ("brand", "product"):
            for invalid in (42, True, ["Acme"], {"name": "Acme"}):
                report = ev.score_predictions([row(0)], [prediction(0, **{field:invalid})])
                self.assertEqual(report["counts"]["failed"], 1)
                self.assertEqual(report["capacity"]["correct"], 0)
            report = ev.score_predictions([row(0)], [prediction(0, **{field:"  "})])
            self.assertEqual(report["counts"]["valid"], 1)
            self.assertEqual(report["counts"]["abstained_identity"], 1)
            self.assertEqual(report["capacity"]["correct"], 1)
            self.assertEqual(report["joint"]["correct"], 0)

    def test_malformed_capacity_cannot_count_as_exact_integer_success(self):
        for capacity in (True, 330.0, "330", -1, 0):
            report = ev.score_predictions([row(0)], [prediction(0, capacity_ml=capacity)])
            self.assertEqual(report["joint"]["correct"], 0)
            self.assertEqual(report["counts"]["failed"], 1)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.rows = []
        for i in range(250):
            value = row(i, "train" if i < 150 else "validation" if i < 175 else "test")
            value["product"] = f"Lime sparkling water product-{i}"
            value["identity_aliases"] = [f"Acme Lime sparkling water product-{i}", f"Acme Lime seltzer product-{i}"]
            value["background_detail"] = ("kitchen counter", "outdoor table", "store shelf")[i % 3]
            value["drink_family"] = ("water", "soda", "juice", "sports", "energy", "milk", "tea")[i % 7]
            (self.root / value["image_path"]).write_bytes(f"pixels-{i}".encode())
            self.rows.append(value)
        self.policy = ev.freeze_split_policy(self.rows)

    def tearDown(self):
        self.directory.cleanup()

    def test_real_split_policy_admits_reviewed_250_and_detects_alias_mutation(self):
        counts = ev.validate_manifest(self.rows, self.root, self.policy)
        self.assertEqual(counts, dict(train=150, validation=25, test=75))
        self.rows[0]["identity_aliases"].append("anything")
        with self.assertRaisesRegex(ValueError, "frozen|fingerprint"):
            ev.validate_manifest(self.rows, self.root, self.policy)

    def test_preregistered_full_brand_variant_is_accepted_and_frozen(self):
        rows = copy.deepcopy(self.rows)
        rows[0].update(brand="President's Choice", brand_aliases=["PC"], product="Lime sparkling water",
            identity_aliases=["President's Choice Lime sparkling water", "PC Lime sparkling water"])
        policy = ev.freeze_split_policy(rows)
        self.assertEqual(ev.validate_manifest(rows, self.root, policy), dict(train=150, validation=25, test=75))
        self.assertEqual(ev.score_predictions([rows[0]], [prediction(0, brand="PC")])["joint"]["correct"], 1)
        old_alias_fingerprint = policy["aliases_sha256"]
        rows[0]["brand_aliases"].append("President Choice")
        self.assertNotEqual(ev.freeze_split_policy(rows)["aliases_sha256"], old_alias_fingerprint)
        with self.assertRaisesRegex(ValueError, "frozen|fingerprint"):
            ev.validate_manifest(rows, self.root, policy)

    def test_bare_brand_variants_and_invalid_brand_alias_lists_are_rejected(self):
        for bare in ("PC", "President's Choice"):
            rows = copy.deepcopy(self.rows)
            rows[0].update(brand="President's Choice", brand_aliases=["PC", "President"], identity_aliases=[bare])
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))
        for invalid in ("PC", None, [""], [42]):
            rows = copy.deepcopy(self.rows)
            rows[0]["brand_aliases"] = invalid
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_missing_reviews_bad_license_unsupported_capacity_or_alias_are_rejected(self):
        for changes in ({"review_status":"pending"}, {"license":"unknown"},
                        {"capacity_evidence":""}, {"capacity_visible":False},
                        {"identity_aliases":["water"]}, {"author":""}, {"source_url":"file:///secret"}):
            rows = copy.deepcopy(self.rows)
            rows[0].update(changes)
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_full_identity_overlap_different_barcodes_and_sizes_cannot_cross_splits(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]["capacity_ml"] = 500
        rows[-1]["capacity_evidence"] = "Printed 500 mL on front"
        rows[-1]["identity_aliases"].append("ＡＣＭＥ   LIME—seltzer product-0")
        self.assertNotEqual(rows[0]["source_product_id"], rows[-1]["source_product_id"])
        self.assertNotEqual(rows[0]["image_sha256"], rows[-1]["image_sha256"])
        with self.assertRaisesRegex(ValueError, "identity.*split"):
            ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_full_identity_size_variants_can_share_one_split_without_brand_only_grouping(self):
        rows = copy.deepcopy(self.rows)
        rows[1]["capacity_ml"] = 500
        rows[1]["capacity_evidence"] = "Printed 500 mL on front"
        rows[1]["identity_aliases"].append(rows[0]["identity_aliases"][0])
        self.assertEqual(ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows)),
                         dict(train=150, validation=25, test=75))

    def test_duplicate_identity_bytes_or_product_across_splits_is_rejected(self):
        for key in ("image_id", "image_sha256", "original_sha256", "source_product_id"):
            rows = copy.deepcopy(self.rows)
            rows[-1][key] = rows[0][key]
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_image_path_traversal_symlink_and_hash_tampering_are_rejected(self):
        for bad_path in ("../outside.jpg", str(self.root / "0.jpg")):
            rows = copy.deepcopy(self.rows)
            rows[0]["image_path"] = bad_path
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))
        (self.root / "link.jpg").symlink_to(self.root / "0.jpg")
        rows = copy.deepcopy(self.rows)
        rows[0]["image_path"] = "link.jpg"
        with self.assertRaises(ValueError):
            ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))
        (self.root / "0.jpg").write_bytes(b"replaced pixels")
        with self.assertRaises(ValueError):
            ev.validate_manifest(self.rows, self.root, self.policy)

    def test_review_identity_and_near_duplicate_cluster_cannot_be_omitted_or_leak(self):
        for field in ("reviewer", "background_detail"):
            rows = copy.deepcopy(self.rows)
            rows[0].pop(field)
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))
        rows = copy.deepcopy(self.rows)
        rows[0]["duplicate_group_id"] = "visually-same"
        rows[-1]["duplicate_group_id"] = "visually-same"
        with self.assertRaises(ValueError):
            ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_all_studio_or_one_natural_test_setting_is_rejected(self):
        all_studio = copy.deepcopy(self.rows)
        for value in all_studio:
            value.update(background="studio", background_detail="white backdrop")
        one_test_setting = copy.deepcopy(self.rows)
        for value in one_test_setting:
            if value["split"] == "test":
                value["background_detail"] = "kitchen counter"
        for rows in (all_studio, one_test_setting):
            with self.assertRaisesRegex(ValueError, "diversity"):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_natural_dataset_and_test_minimum_counts_are_independent(self):
        for overall_natural, test_natural in ((99, 30), (100, 29)):
            rows = copy.deepcopy(self.rows)
            for index, value in enumerate(rows):
                natural = (index < overall_natural - test_natural
                           or 175 <= index < 175 + test_natural)
                if not natural:
                    value.update(background="studio", background_detail="white backdrop")
            with self.assertRaisesRegex(ValueError, "diversity"):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_exact_diversity_minimums_pass_and_are_frozen_in_policy(self):
        rows = copy.deepcopy(self.rows)
        for index, value in enumerate(rows):
            if not (index < 70 or 175 <= index < 205):
                value.update(background="studio", background_detail="white backdrop")
        policy = ev.freeze_split_policy(rows)
        self.assertEqual(ev.validate_manifest(rows, self.root, policy),
                         dict(train=150, validation=25, test=75))
        policy["diversity_requirements"]["minimum_natural_test"] = 0
        with self.assertRaisesRegex(ValueError, "frozen|fingerprint"):
            ev.validate_manifest(rows, self.root, policy)

    def test_homogeneous_families_overweight_family_and_one_test_family_are_rejected(self):
        homogeneous = copy.deepcopy(self.rows)
        for value in homogeneous:
            value["drink_family"] = "wine"
        overweight = copy.deepcopy(self.rows)
        for index, value in enumerate(overweight):
            value["drink_family"] = "wine" if index < 76 else ("water", "soda", "juice", "sports", "energy", "milk")[index % 6]
        one_test_family = copy.deepcopy(self.rows)
        for index, value in enumerate(one_test_family):
            value["drink_family"] = "wine" if value["split"] == "test" else ("water", "soda", "juice", "sports", "energy", "milk")[index % 6]
        only_five_families = copy.deepcopy(self.rows)
        insufficient_sixth_family = copy.deepcopy(self.rows)
        for index in range(250):
            family = ("water", "soda", "juice", "sports", "energy")[index % 5]
            only_five_families[index]["drink_family"] = family
            insufficient_sixth_family[index]["drink_family"] = "wine" if index < 9 else family
        for rows in (homogeneous, overweight, one_test_family, only_five_families, insufficient_sixth_family):
            with self.assertRaisesRegex(ValueError, "family"):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

    def test_family_maximum_75_and_exact_six_overall_five_test_families_pass(self):
        rows = copy.deepcopy(self.rows)
        for index, value in enumerate(rows):
            value["drink_family"] = "wine" if index < 75 else ("water", "soda", "juice", "sports", "energy")[index % 5]
        self.assertEqual(ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows)),
                         dict(train=150, validation=25, test=75))

    def test_family_is_reviewed_enum_and_limits_are_frozen(self):
        for invalid in (None, "Water", "beverage", ""):
            rows = copy.deepcopy(self.rows)
            rows[0]["drink_family"] = invalid
            with self.assertRaisesRegex(ValueError, "family"):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))
        policy = copy.deepcopy(self.policy)
        policy["family_requirements"]["maximum_photos_per_family"] = 250
        with self.assertRaisesRegex(ValueError, "frozen|fingerprint"):
            ev.validate_manifest(self.rows, self.root, policy)

    def test_insufficient_dataset_cannot_pass_using_small_easy_test(self):
        rows = self.rows[:10]
        with self.assertRaises(ValueError):
            ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))


class ProvenanceTests(ManifestTests):
    def prepare_run(self, kind="baseline", dataset_kind="synthetic_fixture"):
        manifest_path = self.root / "manifest.jsonl"
        manifest_path.write_text("".join(json.dumps(r) + "\n" for r in self.rows))
        policy_path = self.root / "policy.json"
        policy_path.write_text(json.dumps(self.policy))
        prompt_path = self.root / "prompt.txt"
        prompt_path.write_text("Identify beverage and printed capacity from pixels only.")
        predictions_path = self.root / "predictions.jsonl"
        predictions_path.write_text("".join(json.dumps(prediction(i, product=self.rows[i]["product"], prompt_sha256=sha(prompt_path.read_bytes()))) + "\n" for i in range(175, 250)))
        metadata = dict(schema_version="beverage-run-v1", run_id="offline-fixture", run_kind=kind,
            dataset_kind=dataset_kind, model_id="meta/test", base_revision="a"*40,
            prompt_path="prompt.txt", prompt_sha256=sha(prompt_path.read_bytes()), manifest_sha256=ev.manifest_sha256(self.rows),
            split_policy_sha256=ev.canonical_sha256(self.policy), predictions_sha256=sha(predictions_path.read_bytes()),
            selected_using="train_validation_only", checkpoint_frozen_utc="2026-11-02T10:00:00Z",
            test_inference_started_utc="2026-11-02T11:00:00Z", adapter_sha256=None)
        self.write_runtime_provenance(metadata)
        metadata_path = self.root / "run.json"
        metadata_path.write_text(json.dumps(metadata))
        return dict(manifest_path=manifest_path, predictions_path=predictions_path,
            policy_path=policy_path, policy_sha256=ev.canonical_sha256(self.policy),
            run_metadata_path=metadata_path, data_root=self.root, artifact_root=self.root), metadata

    def write_runtime_provenance(self, metadata):
        metadata.update(runtime_revision="c"*40, executable_sha256="d"*64, inference_split="test",
            runtime_patch_sha256="9"*64, vision_release_policy="hydra-frozen-vision-release-v1", vision_release_enabled=True)
        model = dict(schema_version="meta-base-provenance-v1", repo=metadata["model_id"],
            revision=metadata["base_revision"], files={"model.safetensors":dict(bytes=10, sha256="e"*64,
                provider_lfs_sha256="e"*64, provider_git_blob_sha1=None)})
        model_path = self.root / "model-provenance.json"
        model_path.write_text(json.dumps(model))
        metadata.update(model_provenance_path=model_path.name, model_provenance_sha256=sha(model_path.read_bytes()),
                        adapter_config_sha256=None)
        if metadata.get("adapter_sha256") is not None:
            adapter_config = self.root / "adapter_config.json"
            adapter_config.write_text(json.dumps(dict(num_layers=1, lora_parameters=dict(rank=4, scale=8))))
            metadata.update(adapter_config_path=adapter_config.name, adapter_config_sha256=sha(adapter_config.read_bytes()))
        config = dict(schema_version="beverage-inference-config-v1", model_id=metadata["model_id"],
            base_revision=metadata["base_revision"], runtime_revision=metadata["runtime_revision"],
            runtime_patch_sha256=metadata["runtime_patch_sha256"], vision_release_policy=metadata["vision_release_policy"],
            vision_release_enabled=metadata["vision_release_enabled"], executable_sha256=metadata["executable_sha256"], model_provenance_sha256=metadata["model_provenance_sha256"],
            prompt_sha256=metadata["prompt_sha256"], generation_header=" to=user<|message|>",
            template_current_date="2026-11-02", reasoning_strength="low", image_tokens=128,
            prefill_step=32, max_output_tokens=96, memory_limit_bytes=19*1024**3, rss_limit_bytes=20*1024**3,
            decoding="greedy", adapter_config_sha256=metadata["adapter_config_sha256"])
        config_path = self.root / "inference-config.json"
        config_path.write_text(json.dumps(config))
        metadata.update(inference_config_path=config_path.name, inference_config_sha256=ev.canonical_sha256(config))
        runtime = {key: config[key] for key in ("model_id", "base_revision", "runtime_revision", "image_tokens",
            "prefill_step", "max_output_tokens", "generation_header", "template_current_date", "reasoning_strength",
            "prompt_sha256", "executable_sha256", "model_provenance_sha256", "adapter_config_sha256", "decoding",
            "memory_limit_bytes", "rss_limit_bytes", "runtime_patch_sha256", "vision_release_policy", "vision_release_enabled")}
        runtime["predictions_sha256"] = metadata["predictions_sha256"]
        runtime_path = self.root / "runtime.json"
        runtime_path.write_text(json.dumps(runtime))
        metadata.update(runtime_config_path=runtime_path.name, runtime_config_sha256=sha(runtime_path.read_bytes()))
        selection_path = self.root / "selection.json"
        selection = dict(adapter_sha256=metadata.get("adapter_sha256"), selected_using="train_validation_only",
            split_policy_sha256=metadata["split_policy_sha256"], checkpoint_frozen_utc=metadata["checkpoint_frozen_utc"],
            validation_image_ids=[r["image_id"] for r in self.rows[150:175]],
            inference_config_sha256=metadata["inference_config_sha256"], adapter_config_sha256=metadata["adapter_config_sha256"])
        selection_path.write_text(json.dumps(selection))
        metadata.update(selection_path=selection_path.name, selection_sha256=sha(selection_path.read_bytes()))

    def prepare_cached_run(self, *, adapter=False, failed=None, missing=None, encoder_changes=None):
        args, metadata = self.prepare_run("adapter" if adapter else "baseline")
        if adapter:
            path = self.root / "adapter.safetensors"
            path.write_bytes(b"synthetic fixture adapter, not trained weights")
            metadata.update(adapter_path=path.name, adapter_sha256=sha(path.read_bytes()))
            args["predictions_path"].write_text("".join(json.dumps(prediction(i, product=self.rows[i]["product"],
                adapter_sha256=metadata["adapter_sha256"], prompt_sha256=metadata["prompt_sha256"]))+"\n" for i in range(175,250)))
        predictions = [json.loads(line) for line in args["predictions_path"].read_text().splitlines()]
        for pred in predictions:
            if pred["image_id"] == failed:
                pred.update(outcome="error", error="feature_preparation_failed", brand=None, product=None, capacity_ml=None)
        predictions = [pred for pred in predictions if pred["image_id"] != missing]
        args["predictions_path"].write_text("".join(json.dumps(pred)+"\n" for pred in predictions))
        metadata["predictions_sha256"] = sha(args["predictions_path"].read_bytes())
        self.write_runtime_provenance(metadata)
        model_path = self.root / metadata["model_provenance_path"]
        model = json.loads(model_path.read_text())
        for index,name in enumerate(("processor_config.json","tokenizer.json","tokenizer_config.json","chat_template.jinja"),1):
            model["files"][name] = dict(bytes=10,sha256=str(index)*64,provider_lfs_sha256=str(index)*64,provider_git_blob_sha1=None)
        model_path.write_text(json.dumps(model))
        metadata["model_provenance_sha256"] = sha(model_path.read_bytes())
        config = json.loads((self.root / metadata["inference_config_path"]).read_text())
        config.update(execution_policy="separate-frozen-vision-v1", vision_release_policy="separate-frozen-vision-v1",
            vision_release_enabled=False, model_provenance_sha256=metadata["model_provenance_sha256"])
        encoder = {key:config[key] for key in ("model_id","base_revision","model_provenance_sha256","runtime_revision",
            "runtime_patch_sha256","executable_sha256","prompt_sha256","generation_header","template_current_date",
            "reasoning_strength","image_tokens")}
        encoder.update(schema_version="beverage-encoder-config-v1",execution_policy="separate-frozen-vision-v1",
            processor_sha256="1"*64,tokenizer_sha256="2"*64,tokenizer_config_sha256="3"*64,chat_template_sha256="4"*64,
            feature_format="safetensors-v1",feature_dtype_policy="frozen_encoder_output",token_dtype="I32")
        encoder.update(encoder_changes or {})
        config["encoder_config_sha256"] = ev.canonical_sha256(encoder)
        metadata.update(execution_policy=config["execution_policy"], vision_release_policy=config["vision_release_policy"],
            vision_release_enabled=False,encoder_config_sha256=config["encoder_config_sha256"],
            language_started_utc=metadata["test_inference_started_utc"])
        config_path = self.root / metadata["inference_config_path"]
        config_path.write_text(json.dumps(config))
        metadata["inference_config_sha256"] = ev.canonical_sha256(config)
        selection_path = self.root / metadata["selection_path"]
        selection = json.loads(selection_path.read_text())
        selection.update(inference_config_sha256=metadata["inference_config_sha256"],encoder_config_sha256=metadata["encoder_config_sha256"])
        selection_path.write_text(json.dumps(selection))
        metadata["selection_sha256"] = sha(selection_path.read_bytes())
        metadata.update(cache_admission_selection_path=selection_path.name,cache_admission_selection_sha256=metadata["selection_sha256"])
        def write_cache(split):
            cache_root = self.root / (split+"-features")
            cache_root.mkdir(exist_ok=True)
            (cache_root / "encoder-config.json").write_text(json.dumps(encoder))
            started = "2026-11-02T10:10:00Z" if split=="test" else "2026-11-02T08:00:00Z"
            completed = "2026-11-02T10:20:00Z" if split=="test" else "2026-11-02T08:30:00Z"
            encoder_run = dict(schema_version="beverage-encoder-run-v1",encoder_config_sha256=metadata["encoder_config_sha256"],
                vision_only=True,language_loaded=False,loaded_weight_namespaces=["vision_tower","vision_adapter","vision_projection"],
                started_utc=started,completed_utc=completed)
            (cache_root / "encoder-run.json").write_text(json.dumps(encoder_run))
            entries=[]
            for truth in [r for r in self.rows if r["split"]==split]:
                entry=dict(image_id=truth["image_id"],image_sha256=truth["image_sha256"],split=split,
                    outcome="success",error=None,tensor_path=truth["image_id"]+".safetensors",feature_key="vision_features",
                    feature_dtype="BF16",feature_shape=[1,6656],tokens_key="prompt_tokens",tokens_dtype="I32",tokens_shape=[3])
                tokens=struct.pack("<iii",1,12,2)
                features=b"\0"*(6656*2)
                header=dict(vision_features=dict(dtype="BF16",shape=[1,6656],data_offsets=[0,len(features)]),
                    prompt_tokens=dict(dtype="I32",shape=[3],data_offsets=[len(features),len(features)+len(tokens)]))
                encoded=json.dumps(header,separators=(",",":")).encode()
                data=struct.pack("<Q",len(encoded))+encoded+features+tokens
                (cache_root / entry["tensor_path"]).write_bytes(data)
                entry.update(tensor_sha256=sha(data),prompt_tokens_sha256=sha(tokens))
                if truth["image_id"]==failed:
                    entry.update({key:None for key in entry if key not in ("image_id","image_sha256","split","outcome","error")})
                    entry.update(outcome="error",error="feature_preparation_failed")
                entries.append(entry)
            descriptor=dict(schema_version="beverage-feature-cache-v1",execution_policy="separate-frozen-vision-v1",
                encoder_config_sha256=metadata["encoder_config_sha256"],encoder_config_path="encoder-config.json",
                encoder_run_path="encoder-run.json",encoder_run_sha256=sha((cache_root / "encoder-run.json").read_bytes()),
                source_manifest_sha256=metadata["manifest_sha256"],split_policy_sha256=metadata["split_policy_sha256"],
                split=split,started_utc=started,completed_utc=completed,outcome="complete",
                cache_admission_selection_sha256=metadata["selection_sha256"] if split=="test" else None,entries=entries)
            descriptor_path=cache_root / "feature-cache.json"
            descriptor_path.write_text(json.dumps(descriptor))
            uses=[dict(image_id=e["image_id"],feature_sha256=e["tensor_sha256"]) for e in entries
                  if e["outcome"]=="success" and e["image_id"]!=missing]
            return descriptor_path,uses
        path,uses=write_cache("test")
        metadata.update(feature_cache_path=path.relative_to(self.root).as_posix(),feature_cache_sha256=sha(path.read_bytes()),
            encoder_config_path=(path.parent / "encoder-config.json").relative_to(self.root).as_posix())
        runtime=json.loads((self.root / metadata["runtime_config_path"]).read_text())
        runtime.update({key:metadata[key] for key in ("model_provenance_sha256","vision_release_policy","vision_release_enabled",
            "execution_policy","encoder_config_sha256","feature_cache_sha256","language_started_utc")})
        runtime.update(language_only=True,vision_loaded=False,actual_feature_uses=uses)
        runtime_path=self.root / metadata["runtime_config_path"]
        runtime_path.write_text(json.dumps(runtime))
        metadata["runtime_config_sha256"]=sha(runtime_path.read_bytes())
        if adapter:
            train_cache,train_uses=write_cache("train")
            training=dict(schema_version="beverage-training-v1",updated_steps=150,initial_adapter_sha256="f"*64,
                adapter_sha256=metadata["adapter_sha256"],parameter_delta_l2=.5,save_reload_max_abs_error=0.,
                split_policy_sha256=metadata["split_policy_sha256"],train_manifest_sha256=ev.manifest_sha256(self.rows[:150]),
                train_image_ids=[r["image_id"] for r in self.rows[:150]],execution_policy=metadata["execution_policy"],
                language_only=True,vision_loaded=False,encoder_config_sha256=metadata["encoder_config_sha256"],
                feature_cache_sha256=sha(train_cache.read_bytes()),feature_cache_path=train_cache.relative_to(self.root).as_posix(),
                encoder_config_path=(train_cache.parent / "encoder-config.json").relative_to(self.root).as_posix(),
                language_started_utc="2026-11-02T09:00:00Z",actual_feature_uses=train_uses)
            train_path=self.root / "training.json"
            train_path.write_text(json.dumps(training))
            metadata.update(training_run_path=train_path.name,training_run_sha256=sha(train_path.read_bytes()))
        args["run_metadata_path"].write_text(json.dumps(metadata))
        return args,metadata

    def rewrite_cache(self,args,metadata,descriptor):
        path=self.root / metadata["feature_cache_path"]
        path.write_text(json.dumps(descriptor))
        metadata["feature_cache_sha256"]=sha(path.read_bytes())
        runtime_path=self.root / metadata["runtime_config_path"]
        runtime=json.loads(runtime_path.read_text())
        runtime["feature_cache_sha256"]=metadata["feature_cache_sha256"]
        by_id={entry["image_id"]:entry for entry in descriptor["entries"]}
        for use in runtime["actual_feature_uses"]:
            if use["image_id"] in by_id and by_id[use["image_id"]].get("tensor_sha256"):
                use["feature_sha256"]=by_id[use["image_id"]]["tensor_sha256"]
        runtime_path.write_text(json.dumps(runtime))
        metadata["runtime_config_sha256"]=sha(runtime_path.read_bytes())
        args["run_metadata_path"].write_text(json.dumps(metadata))

    def test_separate_feature_cache_keeps_failed_and_missing_cases_in_denominator(self):
        args,metadata=self.prepare_cached_run(failed="image-175",missing="image-176")
        report=ev.evaluate_files(**args)
        self.assertEqual(report["joint"]["total"],75)
        self.assertEqual(report["joint"]["correct"],73)
        self.assertEqual(report["counts"]["missing"],1)
        self.assertEqual(report["counts"]["failed"],1)
        self.assertEqual(report["feature_cache_sha256"],metadata["feature_cache_sha256"])

    def test_shared_test_cache_admission_may_differ_but_cannot_predate_later_run_selection(self):
        args,metadata=self.prepare_cached_run()
        admission=json.loads((self.root / metadata["selection_path"]).read_text())
        admission.update(adapter_sha256="a"*64,inference_config_sha256="8"*64)
        path=self.root / "shared-cache-admission.json"
        path.write_text(json.dumps(admission))
        metadata.update(cache_admission_selection_path=path.name,cache_admission_selection_sha256=sha(path.read_bytes()))
        descriptor=json.loads((self.root / metadata["feature_cache_path"]).read_text())
        descriptor["cache_admission_selection_sha256"]=metadata["cache_admission_selection_sha256"]
        self.rewrite_cache(args,metadata,descriptor)
        self.assertEqual(ev.evaluate_files(**args)["joint"]["correct"],75)
        selection_path=self.root / metadata["selection_path"]
        selection=json.loads(selection_path.read_text())
        selection["checkpoint_frozen_utc"]="2026-11-02T10:11:00Z"
        selection_path.write_text(json.dumps(selection))
        metadata.update(checkpoint_frozen_utc=selection["checkpoint_frozen_utc"],selection_sha256=sha(selection_path.read_bytes()))
        args["run_metadata_path"].write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_separate_cache_validates_actual_training_feature_use(self):
        args,metadata=self.prepare_cached_run(adapter=True)
        report=ev.evaluate_files(**args)
        self.assertEqual(report["joint"]["correct"],75)
        self.assertFalse(report["adapter_target_met"])
        training_path=self.root / metadata["training_run_path"]
        training=json.loads(training_path.read_text())
        training["actual_feature_uses"].pop()
        training_path.write_text(json.dumps(training))
        metadata["training_run_sha256"]=sha(training_path.read_bytes())
        args["run_metadata_path"].write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_feature_cache_image_split_timing_and_duplicate_bindings_are_checked(self):
        for mutate in (lambda d:d["entries"][0].update(image_sha256="f"*64),
            lambda d:d["entries"][0].update(split="train"), lambda d:d.update(split="validation"),
            lambda d:d.update(started_utc="2026-11-02T09:00:00Z"),
            lambda d:d.update(completed_utc="2026-11-02T12:00:00Z"),
            lambda d:d["entries"].append(dict(d["entries"][0])),
            lambda d:d["entries"][0].update(tensor_path="../escape.safetensors")):
            args,metadata=self.prepare_cached_run()
            descriptor=json.loads((self.root / metadata["feature_cache_path"]).read_text())
            mutate(descriptor)
            self.rewrite_cache(args,metadata,descriptor)
            with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_feature_tensor_bytes_headers_and_prompt_tokens_are_verified(self):
        for mutation in ("bytes","tokens_hash","shape","overlap","extra_tensor","bool_shape"):
            args,metadata=self.prepare_cached_run()
            descriptor=json.loads((self.root / metadata["feature_cache_path"]).read_text())
            entry=descriptor["entries"][0]
            path=(self.root / metadata["feature_cache_path"]).parent / entry["tensor_path"]
            if mutation=="bytes":path.write_bytes(b"tampered")
            elif mutation=="tokens_hash":entry["prompt_tokens_sha256"]="f"*64
            elif mutation=="shape":entry["feature_shape"]=[1,6655]
            else:
                raw=path.read_bytes(); size=struct.unpack("<Q",raw[:8])[0]
                header=json.loads(raw[8:8+size]); payload=raw[8+size:]
                if mutation=="overlap":header["prompt_tokens"]["data_offsets"]=[0,12]
                elif mutation=="bool_shape":header["vision_features"]["shape"]=[True,6656]
                else:header["answer"]=dict(dtype="I32",shape=[1],data_offsets=[0,4])
                encoded=json.dumps(header).encode();raw=struct.pack("<Q",len(encoded))+encoded+payload
                path.write_bytes(raw);entry["tensor_sha256"]=sha(raw)
            self.rewrite_cache(args,metadata,descriptor)
            with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_separate_runtime_must_prove_language_only_and_match_actual_feature_uses(self):
        for mutate in (lambda r:r.update(vision_loaded=True),lambda r:r.update(language_only=False),
            lambda r:r["actual_feature_uses"].pop(),
            lambda r:r["actual_feature_uses"][0].update(feature_sha256="f"*64),
            lambda r:r["actual_feature_uses"].append(dict(image_id="outside-split",feature_sha256=None))):
            args,metadata=self.prepare_cached_run()
            path=self.root / metadata["runtime_config_path"]
            runtime=json.loads(path.read_text());mutate(runtime);path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"]=sha(path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_encoder_settings_and_actual_vision_only_namespaces_are_bound(self):
        args,metadata=self.prepare_cached_run(encoder_changes={"processor_sha256":"f"*64})
        with self.assertRaises(ValueError):ev.evaluate_files(**args)
        args,metadata=self.prepare_cached_run()
        descriptor_path=self.root / metadata["feature_cache_path"]
        descriptor=json.loads(descriptor_path.read_text())
        path=descriptor_path.parent / descriptor["encoder_run_path"]
        encoder_run=json.loads(path.read_text())
        encoder_run.update(language_loaded=True,loaded_weight_namespaces=["language_model"])
        path.write_text(json.dumps(encoder_run));descriptor["encoder_run_sha256"]=sha(path.read_bytes())
        self.rewrite_cache(args,metadata,descriptor)
        with self.assertRaises(ValueError):ev.evaluate_files(**args)

    def test_inference_settings_or_binary_change_after_selection_is_rejected(self):
        for field, value in (("image_tokens",256), ("prefill_step",64), ("max_output_tokens",192),
            ("decoding","sample"), ("executable_sha256","f"*64), ("generation_header","different"),
            ("template_current_date","2026-11-03"), ("reasoning_strength","high")):
            args, metadata = self.prepare_run()
            config_path = self.root / metadata["inference_config_path"]
            config = json.loads(config_path.read_text())
            config[field] = value
            config_path.write_text(json.dumps(config))
            metadata["inference_config_sha256"] = ev.canonical_sha256(config)
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_actual_runtime_provenance_must_match_selected_configuration(self):
        for field, value in (("prompt_sha256","f"*64), ("executable_sha256","f"*64),
                ("model_provenance_sha256","f"*64), ("adapter_config_sha256","f"*64), ("decoding","sample")):
            args, metadata = self.prepare_run()
            path = self.root / metadata["runtime_config_path"]
            runtime = json.loads(path.read_text())
            runtime[field] = value
            path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"] = sha(path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_actual_runtime_memory_limits_must_match_frozen_limits(self):
        for field, changed in (("memory_limit_bytes",18*1024**3), ("rss_limit_bytes",19*1024**3)):
            args, metadata = self.prepare_run()
            path = self.root / metadata["runtime_config_path"]
            runtime = json.loads(path.read_text())
            runtime[field] = changed
            path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"] = sha(path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_memory_bounds_cannot_be_relaxed_even_in_a_consistent_selection(self):
        for field, invalid in (("memory_limit_bytes",19*1024**3+1), ("memory_limit_bytes",16*1024**3-1),
                ("memory_limit_bytes",True), ("rss_limit_bytes",20*1024**3+1),
                ("rss_limit_bytes",0), ("rss_limit_bytes",True)):
            args, metadata = self.prepare_run()
            config_path = self.root / metadata["inference_config_path"]
            config = json.loads(config_path.read_text())
            config[field] = invalid
            config_path.write_text(json.dumps(config))
            metadata["inference_config_sha256"] = ev.canonical_sha256(config)
            runtime_path = self.root / metadata["runtime_config_path"]
            runtime = json.loads(runtime_path.read_text())
            runtime[field] = invalid
            runtime_path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"] = sha(runtime_path.read_bytes())
            selection_path = self.root / metadata["selection_path"]
            selection = json.loads(selection_path.read_text())
            selection["inference_config_sha256"] = metadata["inference_config_sha256"]
            selection_path.write_text(json.dumps(selection))
            metadata["selection_sha256"] = sha(selection_path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_actual_runtime_patch_and_release_flag_must_match_frozen_configuration(self):
        for field, changed in (("runtime_patch_sha256","f"*64), ("vision_release_policy","unreviewed-policy"),
                               ("vision_release_enabled",False), ("vision_release_enabled",1)):
            args, metadata = self.prepare_run()
            path = self.root / metadata["runtime_config_path"]
            runtime = json.loads(path.read_text())
            runtime[field] = changed
            path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"] = sha(path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)
        args, metadata = self.prepare_run()
        metadata["runtime_patch_sha256"] = "f"*64
        args["run_metadata_path"].write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)

    def test_release_policy_requires_versioned_patch_hash_and_actual_boolean_flag(self):
        for field, invalid in (("runtime_patch_sha256","patched"), ("vision_release_policy","unknown"),
                ("vision_release_enabled",1), ("vision_release_enabled",False)):
            args, metadata = self.prepare_run()
            metadata[field] = invalid
            config_path = self.root / metadata["inference_config_path"]
            config = json.loads(config_path.read_text())
            config[field] = invalid
            config_path.write_text(json.dumps(config))
            metadata["inference_config_sha256"] = ev.canonical_sha256(config)
            runtime_path = self.root / metadata["runtime_config_path"]
            runtime = json.loads(runtime_path.read_text())
            runtime[field] = invalid
            runtime_path.write_text(json.dumps(runtime))
            metadata["runtime_config_sha256"] = sha(runtime_path.read_bytes())
            selection_path = self.root / metadata["selection_path"]
            selection = json.loads(selection_path.read_text())
            selection["inference_config_sha256"] = metadata["inference_config_sha256"]
            selection_path.write_text(json.dumps(selection))
            metadata["selection_sha256"] = sha(selection_path.read_bytes())
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_base_provenance_runtime_telemetry_and_baseline_selection_are_verified(self):
        for field in ("model_provenance_path", "runtime_config_path", "selection_path"):
            args, metadata = self.prepare_run()
            (self.root / metadata[field]).write_text("{}")
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)
        args, metadata = self.prepare_run()
        model_path = self.root / metadata["model_provenance_path"]
        model = json.loads(model_path.read_text())
        model["revision"] = "f"*40
        model_path.write_text(json.dumps(model))
        metadata["model_provenance_sha256"] = sha(model_path.read_bytes())
        args["run_metadata_path"].write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)

    def test_fixture_and_baseline_perfect_scores_cannot_claim_adapter_success(self):
        args, metadata = self.prepare_run()
        report = ev.evaluate_files(**args)
        self.assertEqual(report["joint"]["correct"], 75)
        self.assertFalse(report["adapter_target_met"])
        self.assertEqual(report["measurement_class"], "synthetic_fixture")
        metadata["dataset_kind"] = "real_photos"
        args["run_metadata_path"].write_text(json.dumps(metadata))
        report = ev.evaluate_files(**args)
        self.assertEqual(report["measurement_class"], "measured_baseline")
        self.assertFalse(report["adapter_target_met"])

    def test_forged_hash_model_provenance_or_post_test_checkpoint_is_rejected(self):
        for changes in ({"predictions_sha256":"c"*64}, {"model_id":"other/model"},
                        {"checkpoint_frozen_utc":"2026-11-03T00:00:00Z"},
                        {"selected_using":"test"}, {"base_revision":"main"}):
            args, metadata = self.prepare_run()
            metadata.update(changes)
            args["run_metadata_path"].write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                ev.evaluate_files(**args)

    def test_adapter_requires_hashed_update_and_validation_selection_evidence(self):
        args, metadata = self.prepare_run("adapter", "real_photos")
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)
        adapter = self.root / "adapter.safetensors"
        adapter.write_bytes(b"unit fixture, not trained weights")
        adapter_hash = sha(adapter.read_bytes())
        metadata.update(adapter_sha256=adapter_hash, adapter_path=adapter.name,
            training_run_path="training.json", selection_path="selection.json")
        train = dict(schema_version="beverage-training-v1", updated_steps=1,
            initial_adapter_sha256="f"*64, adapter_sha256=adapter_hash, parameter_delta_l2=0.5,
            save_reload_max_abs_error=0.0, split_policy_sha256=metadata["split_policy_sha256"],
            train_manifest_sha256=ev.manifest_sha256(self.rows[:150]),
            train_image_ids=[r["image_id"] for r in self.rows[:150]])
        selection = dict(adapter_sha256=adapter_hash, selected_using="train_validation_only",
            split_policy_sha256=metadata["split_policy_sha256"],
            validation_image_ids=[r["image_id"] for r in self.rows[150:175]])
        for name, obj in (("training", train), ("selection", selection)):
            path = self.root / (name + ".json")
            path.write_text(json.dumps(obj))
            metadata[name + "_run_sha256" if name == "training" else "selection_sha256"] = sha(path.read_bytes())
        # field name is training_run_sha256, matching its evidence path
        args["run_metadata_path"].write_text(json.dumps(metadata))
        self.write_runtime_provenance(metadata)
        # Predictions must identify exactly these adapter bytes.
        args["predictions_path"].write_text("".join(json.dumps(prediction(i, product=self.rows[i]["product"], adapter_sha256=adapter_hash, prompt_sha256=metadata["prompt_sha256"])) + "\n" for i in range(175,250)))
        metadata["predictions_sha256"] = sha(args["predictions_path"].read_bytes())
        self.write_runtime_provenance(metadata)
        args["run_metadata_path"].write_text(json.dumps(metadata))
        report = ev.evaluate_files(**args)
        self.assertTrue(report["adapter_target_met"])
        self.assertIn("not authenticate", report["provenance_limit"])
        adapter_config_path = self.root / metadata["adapter_config_path"]
        adapter_config_path.write_text('{"scale":16}')
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)
        self.write_runtime_provenance(metadata)
        args["run_metadata_path"].write_text(json.dumps(metadata))
        train["train_image_ids"].append("image-175")
        (self.root / "training.json").write_text(json.dumps(train))
        metadata["training_run_sha256"] = sha((self.root / "training.json").read_bytes())
        args["run_metadata_path"].write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)

    def test_prompt_hash_and_json_duplicate_keys_are_not_trusted(self):
        args, metadata = self.prepare_run()
        (self.root / "prompt.txt").write_text("Changed instruction")
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)
        args, metadata = self.prepare_run()
        args["run_metadata_path"].write_text('{"run_kind":"fixture","run_kind":"adapter"}')
        with self.assertRaises(ValueError):
            ev.evaluate_files(**args)

    def test_cli_writes_new_report_and_refuses_overwrite(self):
        args, _ = self.prepare_run()
        output = self.root / "report.json"
        command = [sys.executable, "scripts/evaluate_beverage_adapter.py",
            "--manifest", str(args["manifest_path"]), "--predictions", str(args["predictions_path"]),
            "--split-policy", str(args["policy_path"]), "--split-policy-sha256", args["policy_sha256"],
            "--run-metadata", str(args["run_metadata_path"]), "--data-root", str(self.root),
            "--artifact-root", str(self.root), "--output", str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
