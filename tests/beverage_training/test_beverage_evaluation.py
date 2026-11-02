"""Offline fixtures exercise scoring; these are never measured photo results."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
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

    def test_missing_reviews_bad_license_unsupported_capacity_or_alias_are_rejected(self):
        for changes in ({"review_status":"pending"}, {"license":"unknown"},
                        {"capacity_evidence":""}, {"capacity_visible":False},
                        {"identity_aliases":["water"]}, {"author":""}, {"source_url":"file:///secret"}):
            rows = copy.deepcopy(self.rows)
            rows[0].update(changes)
            with self.assertRaises(ValueError):
                ev.validate_manifest(rows, self.root, ev.freeze_split_policy(rows))

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
        predictions_path.write_text("".join(json.dumps(prediction(i, prompt_sha256=sha(prompt_path.read_bytes()))) + "\n" for i in range(175, 250)))
        metadata = dict(schema_version="beverage-run-v1", run_id="offline-fixture", run_kind=kind,
            dataset_kind=dataset_kind, model_id="meta/test", base_revision="a"*40,
            prompt_path="prompt.txt", prompt_sha256=sha(prompt_path.read_bytes()), manifest_sha256=ev.manifest_sha256(self.rows),
            split_policy_sha256=ev.canonical_sha256(self.policy), predictions_sha256=sha(predictions_path.read_bytes()),
            selected_using="train_validation_only", checkpoint_frozen_utc="2026-11-02T10:00:00Z",
            test_inference_started_utc="2026-11-02T11:00:00Z", adapter_sha256=None)
        metadata_path = self.root / "run.json"
        metadata_path.write_text(json.dumps(metadata))
        return dict(manifest_path=manifest_path, predictions_path=predictions_path,
            policy_path=policy_path, policy_sha256=ev.canonical_sha256(self.policy),
            run_metadata_path=metadata_path, data_root=self.root, artifact_root=self.root), metadata

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
        # Predictions must identify exactly these adapter bytes.
        args["predictions_path"].write_text("".join(json.dumps(prediction(i, adapter_sha256=adapter_hash, prompt_sha256=metadata["prompt_sha256"])) + "\n" for i in range(175,250)))
        metadata["predictions_sha256"] = sha(args["predictions_path"].read_bytes())
        args["run_metadata_path"].write_text(json.dumps(metadata))
        report = ev.evaluate_files(**args)
        self.assertTrue(report["adapter_target_met"])
        self.assertIn("not authenticate", report["provenance_limit"])
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
