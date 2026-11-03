"""Blinded review packets preserve evidence without disclosing grading targets."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import UUID

from ai.beverage_training import evaluation as ev

try:
    from ai.beverage_training import identity_packets as packets
except ImportError:
    packets = None

REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "ai/beverage_training/reports/2026-11-02/identity-equivalence-policy-v1.json"
POLICY_SHA = "46f54ec956bf3c267083a6f9cf0cc033fdbcf385013d81136af1f949aa189f18"
SCRIPT = REPO / "scripts/prepare_beverage_identity_review.py"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def prediction(image_id: str, **changes) -> dict:
    result = dict(image_id=image_id, outcome="success", brand="Acme", product="Lime water",
                  capacity_ml=777, latency_ms=1, error=None, model_id="HIDDEN_MODEL",
                  run_kind="HIDDEN_RUN", checkpoint="HIDDEN_CHECKPOINT", goal="HIDDEN_GOAL")
    result.update(changes)
    return result


class IdentityPacketTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.data = self.root / "data"
        self.data.mkdir()
        self.rows = []
        for i in range(4):
            pixels = f"fixture-photo-{i}".encode()
            (self.data / f"photo-{i}.jpg").write_bytes(pixels)
            self.rows.append(dict(image_id=f"image-{i}", image_path=f"photo-{i}.jpg",
                image_sha256=digest(pixels), split="validation" if i < 3 else "test",
                brand="Acme", product="Lime water", capacity_ml=777))
        self.predictions = [prediction("image-0"), prediction("image-1", outcome="error", error="HIDDEN_ERROR")]
        self.bindings = dict(manifest_sha256=ev.manifest_sha256(self.rows),
            split_policy_sha256="b"*64, predictions_sha256="c"*64, run_metadata_sha256="d"*64)

    def build(self, output=None, **changes):
        self.assertIsNotNone(packets, "blinded packet component is not implemented")
        args = dict(split="validation", data_root=self.data, output=output or self.root / "review",
                    policy_path=POLICY, source_bindings=self.bindings)
        args.update(changes)
        packets.prepare_identity_packet(self.rows, self.predictions, **args)
        return json.loads((args["output"] / "packet.json").read_text()), json.loads((args["output"] / "packet-map.json").read_text())

    def test_packet_is_identity_only_complete_random_and_source_bound(self):
        packet, mapping = self.build()
        self.assertEqual(set(packet), {"schema_version", "policy_sha256", "blind_id", "created_utc", "rubric", "cases"})
        self.assertEqual(packet["schema_version"], "beverage-identity-packet-v1")
        self.assertEqual(packet["policy_sha256"], POLICY_SHA)
        self.assertEqual(str(UUID(packet["blind_id"])), packet["blind_id"])
        self.assertEqual(set(mapping), {"schema_version", "policy_sha256", *self.bindings, "inference_split", "created_utc", "packet_path", "packet_sha256", "cases"})
        self.assertEqual(mapping["packet_sha256"], digest((self.root / "review/packet.json").read_bytes()))
        self.assertEqual(mapping["packet_path"], "packet.json")
        self.assertEqual(mapping["inference_split"], "validation")
        self.assertEqual(len(packet["cases"]), 3)
        self.assertEqual({c["image_id"] for c in mapping["cases"]}, {"image-0", "image-1", "image-2"})
        mapped = {c["case_id"]: c["image_id"] for c in mapping["cases"]}
        outcomes = {}
        for case in packet["cases"]:
            self.assertEqual(set(case), {"case_id", "image_sha256", "photo_path", "reference", "prediction"})
            self.assertEqual(str(UUID(case["case_id"])), case["case_id"])
            self.assertEqual(case["reference"], {"brand": "Acme", "product": "Lime water"})
            self.assertEqual(set(case["prediction"]), {"outcome", "brand", "product"})
            self.assertTrue(Path(case["photo_path"]).is_absolute())
            outcomes[mapped[case["case_id"]]] = case["prediction"]
        self.assertEqual(outcomes, {"image-0": {"outcome":"success", "brand":"Acme", "product":"Lime water"},
            "image-1": {"outcome":"error", "brand":None, "product":None},
            "image-2": {"outcome":"missing", "brand":None, "product":None}})
        serialized = json.dumps(packet)
        for forbidden in ("capacity", "HIDDEN_", "run_kind", "target", "70%", "image-0"):
            self.assertNotIn(forbidden, serialized)
        second, _ = self.build(output=self.root / "second")
        self.assertNotEqual(packet["blind_id"], second["blind_id"])
        self.assertTrue({c["case_id"] for c in packet["cases"]}.isdisjoint(c["case_id"] for c in second["cases"]))
        policy = json.loads(POLICY.read_text())
        self.assertEqual(packet["rubric"], {key:policy[key] for key in ("identity_requirement", "equivalences", "failures", "review_rule", "reviewer_kind")})

    def test_invalid_outputs_are_sanitized_but_nullable_identity_is_preserved(self):
        self.assertIsNotNone(packets, "identity projection is not implemented")
        for change in ({"brand": ["secret"]}, {"capacity_ml": True}, {"latency_ms": float("nan")}, {"error":"HIDDEN_ERROR"}):
            self.assertEqual(packets.identity_projection(prediction("image-0", **change)),
                             {"outcome":"error", "brand":None, "product":None})
        self.assertEqual(packets.identity_projection(prediction("image-0", brand=None)),
                         {"outcome":"success", "brand":None, "product":"Lime water"})

    def test_duplicate_foreign_and_wrong_split_predictions_rejected_before_writes(self):
        for extra in (self.predictions[0], prediction("foreign"), prediction("image-3")):
            with self.subTest(extra=extra["image_id"]):
                self.predictions.append(extra)
                with self.assertRaises(ValueError): self.build()
                self.assertFalse((self.root / "review").exists())
                self.predictions.pop()

    def test_photo_mutation_traversal_and_symlinks_rejected(self):
        self.assertIsNotNone(packets, "photo validation is not implemented")
        for path in ("../outside.jpg", str(self.data / "photo-0.jpg")):
            with self.subTest(path=path):
                self.rows[0]["image_path"] = path
                self.bindings["manifest_sha256"] = ev.manifest_sha256(self.rows)
                with self.assertRaises(ValueError): self.build()
        self.rows[0]["image_path"] = "photo-0.jpg"
        self.bindings["manifest_sha256"] = ev.manifest_sha256(self.rows)
        original = self.data / "photo-0.jpg"
        original.write_bytes(b"mutated")
        with self.assertRaises(ValueError): self.build()
        original.unlink()
        original.symlink_to(self.data / "photo-1.jpg")
        with self.assertRaises(ValueError): self.build()

    def test_source_policy_and_reference_mutations_rejected(self):
        self.assertIsNotNone(packets, "policy validation is not implemented")
        self.bindings["manifest_sha256"] = "a"*64
        with self.assertRaises(ValueError): self.build()
        self.bindings["manifest_sha256"] = ev.manifest_sha256(self.rows)
        altered = self.root / "policy.json"
        altered.write_bytes(POLICY.read_bytes()+b" ")
        with self.assertRaises(ValueError): self.build(policy_path=altered)
        self.rows[0]["brand"] = None
        self.bindings["manifest_sha256"] = ev.manifest_sha256(self.rows)
        with self.assertRaises(ValueError): self.build()

    def test_existing_output_is_never_modified(self):
        self.build()
        before = {p.name:p.read_bytes() for p in (self.root / "review").iterdir()}
        with self.assertRaises((ValueError, FileExistsError)): self.build()
        self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root / "review").iterdir()})

    def cli(self, paths, **changes):
        args = dict(manifest=paths["manifest"], predictions=paths["predictions"],
            split_policy=paths["policy"], split_policy_sha256=paths["policy_sha"],
            run_metadata=paths["metadata"], data_root=self.data, artifact_root=self.root,
            identity_policy=POLICY, identity_policy_sha256=POLICY_SHA, split="validation", output=self.root / "cli-review")
        args.update(changes)
        command = [sys.executable, str(SCRIPT)]
        for key,value in args.items(): command.extend(["--"+key.replace("_", "-"), str(value)])
        return subprocess.run(command, text=True, capture_output=True)

    def full_fixture(self):
        rows=[]
        for i in range(250):
            pixels=f"full-photo-{i}".encode(); (self.data / f"full-{i}.jpg").write_bytes(pixels)
            product=f"Lime water product-{i}"
            rows.append(dict(image_id=f"full-{i}", image_path=f"full-{i}.jpg", image_sha256=digest(pixels),
                original_sha256=digest(f"original-{i}".encode()), split="train" if i<150 else "validation" if i<175 else "test",
                brand="Acme",product=product,identity_aliases=["Acme "+product],capacity_ml=777,capacity_visible=True,
                capacity_evidence="Printed 777 mL",source_url=f"https://example.org/{i}", source_product_id=f"product-{i}",
                source_revision="2026-11-02",author="Photographer",license="CC-BY-4.0",review_status="reviewed",reviewer="reviewer",
                drink_family=("water","soda","juice","sports","energy","milk","tea")[i%7],
                background="natural", background_detail=("kitchen","park","shop")[i%3]))
        predictions=[prediction("full-150")]
        manifest=self.root/"manifest.jsonl"; manifest.write_text("".join(json.dumps(r)+"\n" for r in rows))
        predictions_path=self.root/"predictions.jsonl";predictions_path.write_text("".join(json.dumps(r)+"\n" for r in predictions))
        policy=ev.freeze_split_policy(rows);policy_path=self.root/"split-policy.json";policy_path.write_text(json.dumps(policy))
        metadata=dict(manifest_sha256=ev.manifest_sha256(rows),split_policy_sha256=ev.canonical_sha256(policy),
                      predictions_sha256=digest(predictions_path.read_bytes()),inference_split="validation")
        metadata_path=self.root/"run.json";metadata_path.write_text(json.dumps(metadata))
        return dict(manifest=manifest,predictions=predictions_path,policy=policy_path,policy_sha=ev.canonical_sha256(policy),metadata=metadata_path)

    def test_cli_validation_binds_real_source_bytes_and_retains_missing_cases(self):
        paths=self.full_fixture()
        result=self.cli(paths)
        self.assertEqual(result.returncode,0,result.stderr)
        packet=json.loads((self.root/"cli-review/packet.json").read_text())
        mapping=json.loads((self.root/"cli-review/packet-map.json").read_text())
        self.assertEqual(len(packet["cases"]),25)
        self.assertEqual(sum(c["prediction"]["outcome"]=="missing" for c in packet["cases"]),24)
        self.assertEqual(mapping["run_metadata_sha256"],digest(paths["metadata"].read_bytes()))
        self.assertEqual(mapping["predictions_sha256"],digest(paths["predictions"].read_bytes()))

    def test_cli_rejects_source_mutation_duplicate_json_and_test_without_selection(self):
        paths=self.full_fixture()
        metadata=paths["metadata"].read_bytes()
        for corrupt in (metadata.replace(b'"inference_split": "validation"', b'"inference_split": "test"'),
                        b'{"inference_split":"validation","inference_split":"validation"}'):
            paths["metadata"].write_bytes(corrupt)
            result=self.cli(paths)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse((self.root/"cli-review").exists())
        paths["metadata"].write_bytes(metadata)
        paths["predictions"].write_text(paths["predictions"].read_text()+"\n")
        self.assertEqual(self.cli(paths).returncode,2)
        self.assertFalse((self.root/"cli-review").exists())
        self.assertEqual(self.cli(paths,split="test").returncode,2)
        self.assertFalse((self.root/"cli-review").exists())

    def test_cli_complete_test_gate_requires_policy_selected_before_inference(self):
        # Reuse the existing deterministic, complete test-provenance fixture;
        # there are no real photos, models or inference side effects here.
        spec = importlib.util.spec_from_file_location("packet_provenance_fixture", Path(__file__).with_name("test_beverage_evaluation.py"))
        fixture_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture_module)
        fixture = fixture_module.ProvenanceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        args, metadata = fixture.prepare_run()
        self.data = fixture.root
        self.root = fixture.root
        paths = dict(manifest=args["manifest_path"],predictions=args["predictions_path"],
            policy=args["policy_path"],policy_sha=args["policy_sha256"],metadata=args["run_metadata_path"])
        selection_path = fixture.root / metadata["selection_path"]
        selection = json.loads(selection_path.read_text())
        selection["identity_policy_sha256"] = "f"*64
        selection_path.write_text(json.dumps(selection))
        metadata["selection_sha256"] = digest(selection_path.read_bytes())
        metadata["test_inference_started_utc"] = "2026-11-03T03:00:00Z"
        paths["metadata"].write_text(json.dumps(metadata))
        self.assertEqual(self.cli(paths,split="test").returncode,2)
        self.assertFalse((self.root/"cli-review").exists())
        selection["identity_policy_sha256"] = POLICY_SHA
        selection_path.write_text(json.dumps(selection))
        metadata["selection_sha256"] = digest(selection_path.read_bytes())
        metadata["test_inference_started_utc"] = "2026-11-02T11:00:00Z"
        paths["metadata"].write_text(json.dumps(metadata))
        self.assertEqual(self.cli(paths,split="test").returncode,2)
        self.assertFalse((self.root/"cli-review").exists())
        metadata["test_inference_started_utc"] = "2026-11-03T03:00:00Z"
        paths["metadata"].write_text(json.dumps(metadata))
        result=self.cli(paths,split="test")
        self.assertEqual(result.returncode,0,result.stderr)
        packet=json.loads((self.root/"cli-review/packet.json").read_text())
        self.assertEqual(len(packet["cases"]),75)
