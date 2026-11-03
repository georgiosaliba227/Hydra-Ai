#!/usr/bin/env python3
"""Offline full-identity review scorer; never runs inference or overwrites results."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai.beverage_training.equivalence import evaluate_equivalence_files


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','predictions','split-policy','run-metadata','data-root','artifact-root','identity-policy','packet-map','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--split-policy-sha256',required=True)
    p.add_argument('--identity-policy-sha256',required=True)
    p.add_argument('--identity-review',type=Path,action='append',required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():raise ValueError('output already exists')
        r=evaluate_equivalence_files(manifest_path=a.manifest,predictions_path=a.predictions,
            policy_path=a.split_policy,policy_sha256=a.split_policy_sha256,run_metadata_path=a.run_metadata,
            data_root=a.data_root,artifact_root=a.artifact_root,identity_policy_path=a.identity_policy,
            identity_policy_sha256=a.identity_policy_sha256,packet_map_path=a.packet_map,identity_review_paths=a.identity_review)
        with a.output.open('x',encoding='utf-8') as stream:
            json.dump(r,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        print(f'Identity evaluation rejected ({type(error).__name__}); check frozen evidence.',file=sys.stderr)
        return 2
    print(f"{r['measurement_class']}: {r['joint']['correct']}/{r['joint']['total']} joint; trained adapter target met={r['adapter_target_met']}")
    return 0


if __name__=='__main__':raise SystemExit(main())
