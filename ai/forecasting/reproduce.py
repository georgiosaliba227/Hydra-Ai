"""Reproduce all independent real experiments, then supplemental synthetic demo."""
import argparse
import json
from pathlib import Path

from .synthetic import generate_scenarios
from .train import train_experiment

SOURCES = {
    "qde-v1": ["https://physionet.org/content/qde/1.0.0/", "Open Data Commons Attribution License v1.0"],
    "spectrophon-v1": ["https://data.mendeley.com/datasets/jt22782wjh/1", "CC BY 4.0"],
}


def reproduce(records: list[dict], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    reports = {}
    for study in sorted(SOURCES):
        selected = [r for r in records if r["study_id"] == study]
        provenance = SOURCES[study] + sorted({"source_sha256:"+r["source_sha256"] for r in selected})
        artifact, report = train_experiment(selected, provenance=provenance)
        artifact["model_version"] = study+"-research-v1"
        (output/(study+".json")).write_text(json.dumps(artifact,indent=2,sort_keys=True,allow_nan=False)+"\n")
        reports[study] = report
    anchors = [r for r in records if r["study_id"] == "spectrophon-v1"]
    scenarios = generate_scenarios(anchors)
    provenance = ["Hydra synthetic mass-balance scenarios v1, seed 8317; targets simulated; baseline covariates bootstrapped from attributed real training anchors"] + SOURCES["spectrophon-v1"]
    artifact, report = train_experiment(scenarios,provenance=provenance)
    artifact["model_version"] = "synthetic-workout-demo-v1"
    (output/"synthetic_demo.json").write_text(json.dumps(artifact,indent=2,sort_keys=True,allow_nan=False)+"\n")
    reports["synthetic"] = report
    (output/"evaluation.json").write_text(json.dumps(reports,indent=2,sort_keys=True,allow_nan=False)+"\n")
    return reports


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--records",required=True,type=Path)
    parser.add_argument("--output",type=Path,default=Path(__file__).with_name("artifacts"))
    args=parser.parse_args()
    reproduce(json.loads(args.records.read_text()),args.output)

if __name__=="__main__":
    main()
