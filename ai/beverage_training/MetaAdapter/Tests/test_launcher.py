"""Launcher validation must run before a model process is launched."""
import importlib.util
from pathlib import Path
import tempfile
import hashlib
import json
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "train_meta_beverage_adapter.py"
spec = importlib.util.spec_from_file_location("meta_launcher", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class LauncherTests(unittest.TestCase):
    def test_high_resolution_adapter_dimensions_stay_bounded_before_model_launch(self):
        launcher.validate_experiment_dimensions(image_tokens=1024, layers=8, rank=16)
        for name, value in (("image_tokens", 1025), ("image_tokens", 15), ("layers", 9), ("layers", 0), ("rank", 17), ("rank", True)):
            dimensions = dict(image_tokens=1024, layers=8, rank=16)
            dimensions[name] = value
            with self.assertRaises(ValueError):
                launcher.validate_experiment_dimensions(**dimensions)

    def test_child_manifest_excludes_held_out_labels_and_training_test_rows(self):
        train = {"image_id": "a", "image_path": "a.jpg", "image_sha256": "a" * 64, "split": "train", "review_status": "reviewed", "brand": "TRAIN LABEL", "product": "type", "capacity_ml": 100, "capacity_visible": True}
        test = {"image_id": "b", "image_path": "b.jpg", "image_sha256": "b" * 64, "split": "test", "review_status": "reviewed", "brand": "HELD OUT LABEL", "source_product_id": "BARCODE"}
        projected = launcher.runtime_rows([train, test], command="infer", split="test")
        self.assertEqual(projected, [{key: test[key] for key in ("image_id", "image_sha256", "split", "review_status")}])
        self.assertEqual(launcher.runtime_rows([train, test], command="train", split="validation"), [{key: value for key, value in train.items() if key != "image_path"}])

    def test_encoder_manifest_is_label_free_but_has_pixels(self):
        row={"image_id":"a","image_path":"a.jpg","image_sha256":"a"*64,"split":"train","review_status":"reviewed","brand":"SECRET","source_product_id":"BARCODE"}
        result=launcher.runtime_rows([row],command="prepare-features",split="train")[0]
        self.assertEqual(set(result),{"image_id","image_path","image_sha256","split","review_status"})

    def test_test_split_requires_frozen_selection(self):
        with self.assertRaises(ValueError):
            launcher.validate_selection(None, split="test", adapter_sha256=None, policy_sha256="a" * 64)

    def test_selection_binds_adapter_and_policy(self):
        selection = {"selected_using": "train_validation_only", "adapter_sha256": "b" * 64, "split_policy_sha256": "a" * 64, "checkpoint_frozen_utc": "2026-11-02T12:00:00Z", "adapter_config_sha256": "c" * 64, "inference_config_sha256": "d" * 64}
        self.assertEqual(launcher.validate_selection(selection, split="test", adapter_sha256="b" * 64, policy_sha256="a" * 64, adapter_config_sha256="c" * 64, inference_config_sha256="d" * 64), "2026-11-02T12:00:00Z")
        with self.assertRaises(ValueError):
            launcher.validate_selection(selection, split="test", adapter_sha256="c" * 64, policy_sha256="a" * 64)

    def test_selection_rejects_changed_decoding_or_adapter_config(self):
        selection = {"selected_using": "train_validation_only", "adapter_sha256": "b" * 64, "split_policy_sha256": "a" * 64, "checkpoint_frozen_utc": "2026-11-02T12:00:00Z", "adapter_config_sha256": "c" * 64, "inference_config_sha256": "d" * 64}
        for config_hash, inference_hash in [("e" * 64, "d" * 64), ("c" * 64, "e" * 64)]:
            with self.assertRaises(ValueError):
                launcher.validate_selection(selection, split="test", adapter_sha256="b" * 64, policy_sha256="a" * 64, adapter_config_sha256=config_hash, inference_config_sha256=inference_hash)

    def test_base_provenance_rejects_mutated_weights_and_escaping_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {name: b"{}" for name in ("config.json", "processor_config.json", "tokenizer.json", "tokenizer_config.json", "generation_config.json", "chat_template.jinja")}
            files["model.safetensors.index.json"] = json.dumps({"weight_map": {"test.weight": "model-00001-of-00001.safetensors"}}).encode()
            files["model-00001-of-00001.safetensors"] = b"test fixture weights"
            records = {}
            for name, data in files.items():
                (root / name).write_bytes(data)
                records[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "provider_lfs_sha256": None, "provider_git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
            proof = {"schema_version": "meta-base-provenance-v1", "repo": "test/repo", "revision": "a" * 40, "files": records}
            path = root / "base-provenance.json"
            path.write_text(json.dumps(proof))
            self.assertEqual(launcher.verify_base_provenance(root, model_id="test/repo", revision="a" * 40)[1], launcher.file_sha(path))
            (root / "model-00001-of-00001.safetensors").write_bytes(b"mutated fixture")
            with self.assertRaises(ValueError):
                launcher.verify_base_provenance(root, model_id="test/repo", revision="a" * 40)
            (root / "model-00001-of-00001.safetensors").write_bytes(files["model-00001-of-00001.safetensors"])
            proof["files"]["../escape"] = records["config.json"]
            path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                launcher.verify_base_provenance(root, model_id="test/repo", revision="a" * 40)

    @unittest.skipUnless(sys.platform == "darwin", "Apple runtime monitor requires macOS")
    def test_real_child_is_stopped_when_resident_budget_is_exceeded(self):
        with self.assertRaises(launcher.LocalProcessError) as caught:
            launcher.run_local_process([sys.executable, "-c", "import time; allocation=bytearray(16*1024*1024); time.sleep(.5)"], rss_limit_bytes=1024*1024)
        self.assertEqual(caught.exception.kind, "rss_budget_exceeded")

    @unittest.skipUnless(sys.platform == "darwin", "Apple runtime monitor requires macOS")
    def test_bounded_normal_child_finishes(self):
        launcher.run_local_process([sys.executable, "-c", "pass"], rss_limit_bytes=256*1024*1024)

    def test_sampler_exit_race_preserves_successful_child_exit(self):
        with patch.object(launcher, "child_resident_bytes", side_effect=launcher.LocalProcessError("resident_measurement_unavailable")):
            launcher.run_local_process([sys.executable, "-c", "import time; time.sleep(.03)"], rss_limit_bytes=256*1024*1024)

    def test_sampler_exit_race_preserves_failed_child_exit(self):
        with patch.object(launcher, "child_resident_bytes", side_effect=launcher.LocalProcessError("resident_measurement_unavailable")):
            with self.assertRaises(launcher.LocalProcessError) as caught:
                launcher.run_local_process([sys.executable, "-c", "import time,sys; time.sleep(.03); sys.exit(7)"], rss_limit_bytes=256*1024*1024)
        self.assertEqual(caught.exception.kind, "local_runtime_failed")

    def test_sampler_fault_on_live_child_still_fails_closed(self):
        with patch.object(launcher, "child_resident_bytes", side_effect=launcher.LocalProcessError("resident_measurement_unavailable")):
            with self.assertRaises(launcher.LocalProcessError) as caught:
                launcher.run_local_process([sys.executable, "-c", "import time; time.sleep(1)"], rss_limit_bytes=256*1024*1024)
        self.assertEqual(caught.exception.kind, "resident_measurement_unavailable")

    def test_artifact_paths_must_resolve_below_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "run" / "training.json"
            child.parent.mkdir(); child.write_text("{}")
            self.assertEqual(launcher.artifact_relative(child, root), "run/training.json")
            with self.assertRaises(ValueError):
                launcher.artifact_relative(root.parent / "outside.json", root)

if __name__ == "__main__":
    unittest.main()
