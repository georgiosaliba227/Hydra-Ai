"""Conservative owner-approved identity equivalence; exact volume stays deterministic.

Pure scoring cannot establish a trained-model result. Final files must also pass
all original frozen experiment/inference checks and two bound review artifacts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from . import evaluation as ev
from .identity_packets import identity_projection, load_identity_policy, RUBRIC_FIELDS

VERDICTS = {'full_identity_equivalent', 'meaningful_identity_error', 'uncertain'}
SOURCE_FIELDS = ('manifest_sha256', 'split_policy_sha256', 'predictions_sha256', 'run_metadata_sha256')


def score_reviewed_predictions(rows: list[dict], predictions: list[dict],
                               decisions: dict[str, tuple[str, str]], *, strata: bool = True) -> dict:
    """Every case remains; both independent equivalent decisions are necessary."""
    legacy = ev.score_predictions(rows, predictions, strata=False)
    ids = {row['image_id'] for row in rows}
    if set(decisions) != ids:
        raise ValueError('reviews must cover every reference exactly once')
    for pair in decisions.values():
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(v not in VERDICTS for v in pair):
            raise ValueError('two recognized review verdicts required per case')
    by_id = {p['image_id']:p for p in predictions}
    old_cases = {c['image_id']:c for c in legacy['cases']}
    cases = []
    counts = dict(legacy['counts'])
    counts.update(identity_correct=0, joint_correct=0)
    for row in rows:
        key = row['image_id']
        source = old_cases[key]
        pred = by_id.get(key)
        complete = bool(pred and source['status'] == 'valid'
            and ev._text(pred.get('brand')) and ev._text(pred.get('product')))
        identity_ok = complete and all(v == 'full_identity_equivalent' for v in decisions[key])
        volume_ok = source['capacity_correct']
        counts['identity_correct'] += identity_ok
        counts['joint_correct'] += identity_ok and volume_ok
        cases.append(dict(image_id=key, status=source['status'], identity_correct=identity_ok,
            capacity_correct=volume_ok, joint_correct=identity_ok and volume_ok,
            legacy_name_alias_correct=source['identity_correct'], review_verdicts=list(decisions[key])))
    total = len(rows)
    report = dict(schema_version='beverage-equivalence-assessment-v1', measurement_class='unverified_review_assessment',
        adapter_target_met=False, counts=counts, identity=ev._metric(counts['identity_correct'],total),
        capacity=legacy['capacity'], joint=ev._metric(counts['joint_correct'],total), coverage=legacy['coverage'],
        above_70_percent=counts['joint_correct']*10 > total*7, cases=cases,
        legacy_name_alias_metrics=legacy,
        review_agreement=dict(total=total, exact_verdict_agreement=sum(a==b for a,b in decisions.values()),
            equivalence_decision_agreement=sum((a=='full_identity_equivalent')==(b=='full_identity_equivalent') for a,b in decisions.values()),
            unanimous_equivalent=sum(a==b=='full_identity_equivalent' for a,b in decisions.values())))
    if strata:
        for name, field in (('backgrounds','background'),('drink_families','drink_family')):
            report[name] = {}
            for value in sorted({row[field] for row in rows}):
                subset = [row for row in rows if row[field] == value]
                subset_ids = {row['image_id'] for row in subset}
                report[name][value] = score_reviewed_predictions(subset,
                    [p for p in predictions if p['image_id'] in subset_ids],
                    {key:decisions[key] for key in subset_ids}, strata=False)
    return report


def _uuid4(value: Any) -> bool:
    if not isinstance(value,str):
        return False
    try:
        parsed=UUID(value)
    except ValueError:
        return False
    return parsed.version==4 and str(parsed)==value


def _artifact_file(root: Path, path: Path) -> Path:
    root = Path(root).absolute()
    path = Path(path).absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError('review artifact outside its authoritative root') from error
    return ev.safe_artifact_path(root, relative.as_posix())


def _json_artifact(root: Path, path: Path) -> tuple[Path, dict]:
    path = _artifact_file(root,path)
    if path.stat().st_size > 4*1024*1024:
        raise ValueError('review artifact exceeds bounded size')
    return path, ev.read_json(path)


def validate_identity_reviews(*, rows: list[dict], predictions: list[dict], data_root: Path,
        artifact_root: Path, mapping_path: Path, review_paths: list[Path], policy_path: Path,
        policy_sha256: str, source_bindings: dict, split: str) -> tuple[dict, dict]:
    """Validate isolated review evidence; no file hashes authenticate visual facts."""
    policy_path = _artifact_file(artifact_root,policy_path)
    policy, actual_policy_sha = load_identity_policy(policy_path)
    if actual_policy_sha != policy_sha256:
        raise ValueError('owner policy fingerprint mismatch')
    mapping_path, mapping = _json_artifact(artifact_root,mapping_path)
    expected_map = {'schema_version','policy_sha256',*SOURCE_FIELDS,'inference_split','created_utc',
        'packet_path','packet_sha256','cases'}
    if (set(mapping) != expected_map or mapping['schema_version'] != 'beverage-identity-packet-map-v1'
            or mapping['policy_sha256'] != policy_sha256 or mapping['inference_split'] != split
            or set(source_bindings) != set(SOURCE_FIELDS)
            or any(not ev._sha(source_bindings[k]) or mapping[k] != source_bindings[k] for k in SOURCE_FIELDS)
            or mapping['manifest_sha256'] != ev.manifest_sha256(rows)):
        raise ValueError('review mapping differs from frozen source evidence')
    packet_path = ev.safe_artifact_path(mapping_path.parent,mapping['packet_path'])
    _, packet = _json_artifact(artifact_root,packet_path)
    if (not ev._sha(mapping['packet_sha256']) or ev.file_sha256(packet_path) != mapping['packet_sha256']
            or set(packet) != {'schema_version','policy_sha256','blind_id','created_utc','rubric','cases'}
            or packet['schema_version'] != 'beverage-identity-packet-v1'
            or packet['policy_sha256'] != policy_sha256 or not _uuid4(packet['blind_id'])
            or packet['rubric'] != {k:policy[k] for k in RUBRIC_FIELDS}
            or packet['created_utc'] != mapping['created_utc']):
        raise ValueError('blind packet or owner rubric changed')
    created = ev._utc(packet['created_utc'])
    if not ev._utc(policy['frozen_utc']) <= created <= datetime.now(timezone.utc):
        raise ValueError('packet must follow frozen policy and precede review')
    selected = {r['image_id']:r for r in rows if r.get('split') == split}
    if not selected or len(selected) != sum(r.get('split') == split for r in rows):
        raise ValueError('nonempty unique reference split required')
    # This also rejects duplicate or foreign source predictions before pairing.
    ev.score_predictions(list(selected.values()),predictions,strata=False)
    by_id = {p['image_id']:p for p in predictions}
    mappings = mapping['cases']
    if not isinstance(mappings,list) or len(mappings) != len(selected):
        raise ValueError('every split case must remain in the mapping')
    by_case, seen = {},set()
    for item in mappings:
        if (not isinstance(item,dict) or set(item) != {'case_id','image_id','image_sha256'}
                or not _uuid4(item['case_id']) or item['case_id'] in by_case
                or item['image_id'] not in selected or item['image_id'] in seen
                or item['image_sha256'] != selected[item['image_id']]['image_sha256']):
            raise ValueError('invalid duplicate or foreign mapped image')
        by_case[item['case_id']] = item['image_id'];seen.add(item['image_id'])
    cases = packet['cases']
    if not isinstance(cases,list) or len(cases) != len(by_case):
        raise ValueError('packet must preserve every mapped case')
    seen = set()
    for case in cases:
        if (not isinstance(case,dict) or set(case) != {'case_id','image_sha256','photo_path','reference','prediction'}
                or case['case_id'] not in by_case or case['case_id'] in seen):
            raise ValueError('duplicate or foreign packet case')
        seen.add(case['case_id']);key = by_case[case['case_id']];row=selected[key]
        photo=ev.safe_artifact_path(Path(data_root),row['image_path'])
        if (case['photo_path'] != str(photo.resolve()) or case['image_sha256'] != row['image_sha256']
                or ev.file_sha256(photo) != row['image_sha256']
                or case['reference'] != {k:row[k] for k in ('brand','product')}
                or case['prediction'] != identity_projection(by_id.get(key))):
            raise ValueError('packet facts/photo differ from actual reference or prediction')
    if len(review_paths) != 2:
        raise ValueError('two independent review files required')
    reviewers, judgments, evidence = set(),[],[]
    for review_path in review_paths:
        review_path, review = _json_artifact(artifact_root,review_path)
        fields={'schema_version','reviewer_id','reviewer_kind','independence_attestation','reviewed_utc',
            'packet_sha256','policy_sha256','cases'}
        if (set(review) != fields or review['schema_version'] != 'beverage-identity-review-v1'
                or not ev._text(review['reviewer_id']) or review['reviewer_id'] in reviewers
                or review['reviewer_kind'] != 'codex_agent'
                or review['independence_attestation'] != 'independent_blind_packet_only'
                or review['packet_sha256'] != mapping['packet_sha256'] or review['policy_sha256'] != policy_sha256
                or not created <= ev._utc(review['reviewed_utc']) <= datetime.now(timezone.utc)):
            raise ValueError('review identity, policy, packet, independence or timing invalid')
        reviewers.add(review['reviewer_id'])
        items=review['cases'];verdicts={}
        if not isinstance(items,list) or len(items) != len(by_case):
            raise ValueError('review must cover every packet case')
        for item in items:
            if (not isinstance(item,dict) or set(item) != {'case_id','verdict','reason','photo_inspected'}
                    or item['case_id'] not in by_case or item['case_id'] in verdicts
                    or item['verdict'] not in VERDICTS or item['photo_inspected'] is not True
                    or not ev._text(item['reason']) or len(item['reason']) > 2000):
                raise ValueError('invalid incomplete uninspected or duplicate judgment')
            key=by_case[item['case_id']];pred=by_id.get(key)
            if item['verdict']=='full_identity_equivalent' and (not pred or not ev._valid_prediction(pred)
                    or not ev._text(pred.get('brand')) or not ev._text(pred.get('product'))):
                raise ValueError('unavailable full source identity cannot be approved')
            verdicts[item['case_id']]=item['verdict']
        judgments.append(verdicts)
        evidence.append(dict(reviewer_id=review['reviewer_id'],reviewer_kind=review['reviewer_kind'],
            review_sha256=ev.file_sha256(review_path),reviewed_utc=review['reviewed_utc']))
    decisions={key:tuple(j[c] for j in judgments) for c,key in by_case.items()}
    return decisions,dict(policy_version=policy['policy_version'],identity_policy_sha256=policy_sha256,
        policy_frozen_utc=policy['frozen_utc'],packet_sha256=mapping['packet_sha256'],
        packet_map_sha256=ev.file_sha256(mapping_path),reviews=evidence)


def _validate_development_run(metadata: dict, rows: list[dict], predictions: list[dict],
        artifact_root: Path, bindings: dict) -> None:
    """Check saved validation artifacts without permitting a final-test claim."""
    if (metadata.get('schema_version') != 'beverage-run-v1' or metadata.get('inference_split') != 'validation'
            or metadata.get('run_kind') not in ('baseline','adapter')
            or any(metadata.get(k) != bindings[k] for k in ('manifest_sha256','split_policy_sha256','predictions_sha256'))):
        raise ValueError('validation source identity differs from saved bytes')
    runtime = ev._evidence(metadata,'runtime_config_path','runtime_config_sha256',artifact_root)
    config = ev._canonical_evidence(metadata,'inference_config_path','inference_config_sha256',artifact_root)
    model = ev._evidence(metadata,'model_provenance_path','model_provenance_sha256',artifact_root)
    if config.get('schema_version') != 'beverage-inference-config-v1':
        raise ValueError('versioned inference configuration required')
    for key,value in config.items():
        if key != 'schema_version' and (key not in runtime or type(runtime[key]) is not type(value) or runtime[key] != value):
            raise ValueError('validation runtime differs from selected configuration')
    for key in ('model_id','base_revision','runtime_revision','executable_sha256','model_provenance_sha256',
                'prompt_sha256','adapter_config_sha256'):
        if key not in metadata or config.get(key) != metadata[key]:
            raise ValueError('validation provenance differs from configuration')
    prompt = ev.safe_artifact_path(artifact_root,metadata.get('prompt_path'))
    if (ev.file_sha256(prompt) != metadata.get('prompt_sha256')
            or runtime.get('predictions_sha256') != metadata['predictions_sha256']
            or model.get('schema_version') != 'meta-base-provenance-v1'
            or model.get('repo') != metadata['model_id'] or model.get('revision') != metadata['base_revision']):
        raise ValueError('validation prompt, predictions or model proof mismatch')
    if config.get('execution_policy') == 'separate-frozen-vision-v1':
        ev.validate_feature_cache(metadata,rows,artifact_root,config,model,runtime,
            split='validation',predictions=predictions)
    if metadata['run_kind'] == 'adapter':
        adapter = ev.safe_artifact_path(artifact_root,metadata.get('adapter_path'))
        training = ev._evidence(metadata,'training_run_path','training_run_sha256',artifact_root)
        train_rows = [r for r in rows if r['split']=='train']
        if (ev.file_sha256(adapter) != metadata.get('adapter_sha256')
                or training.get('schema_version') != 'beverage-training-v1'
                or type(training.get('updated_steps')) is not int or training['updated_steps'] < len(train_rows)
                or training.get('adapter_sha256') != metadata['adapter_sha256']
                or training.get('initial_adapter_sha256') == metadata['adapter_sha256']
                or set(training.get('train_image_ids',[])) != {r['image_id'] for r in train_rows}
                or training.get('train_manifest_sha256') != ev.manifest_sha256(train_rows)
                or training.get('split_policy_sha256') != bindings['split_policy_sha256']
                or type(training.get('parameter_delta_l2')) not in (int,float)
                or not 0 < training['parameter_delta_l2'] < float('inf')
                or type(training.get('save_reload_max_abs_error')) not in (int,float)
                or not 0 <= training['save_reload_max_abs_error'] <= 1e-3):
            raise ValueError('completed train-only update evidence required')
        ev._evidence(metadata,'adapter_config_path','adapter_config_sha256',artifact_root)
        if config.get('execution_policy') == 'separate-frozen-vision-v1':
            ev.validate_feature_cache(training,rows,artifact_root,config,model,training,split='train')
    elif metadata.get('adapter_sha256') is not None:
        raise ValueError('baseline cannot claim adapter weights')
    for pred in predictions:
        if any(pred.get(k) != metadata.get(k) for k in ('model_id','base_revision','prompt_sha256','adapter_sha256')):
            raise ValueError('validation prediction provenance mismatch')


def evaluate_equivalence_files(*, manifest_path: Path, predictions_path: Path, policy_path: Path,
        policy_sha256: str, run_metadata_path: Path, data_root: Path, artifact_root: Path,
        identity_policy_path: Path, identity_policy_sha256: str, packet_map_path: Path,
        identity_review_paths: list[Path]) -> dict:
    """Preserve all original final-run gates; use the owner-approved identity rule."""
    identity_policy_path = _artifact_file(artifact_root,identity_policy_path)
    identity_policy, actual_sha = load_identity_policy(identity_policy_path)
    if actual_sha != identity_policy_sha256:
        raise ValueError('owner identity policy fingerprint mismatch')
    rows = ev.read_jsonl(manifest_path)
    predictions = ev.read_jsonl(predictions_path)
    split_policy = ev.read_json(policy_path)
    if not ev._sha(policy_sha256) or ev.canonical_sha256(split_policy) != policy_sha256:
        raise ValueError('frozen split policy mismatch')
    metadata = ev.read_json(run_metadata_path)
    split = metadata.get('inference_split')
    bindings=dict(manifest_sha256=ev.manifest_sha256(rows),split_policy_sha256=policy_sha256,
        predictions_sha256=ev.file_sha256(predictions_path),run_metadata_sha256=ev.file_sha256(run_metadata_path))
    if split == 'test':
        # Full dataset, model/weights/updates, configuration, cache, selection,
        # inference and prediction provenance remain enforced by the old scorer.
        legacy = ev.evaluate_files(manifest_path=manifest_path,predictions_path=predictions_path,
            policy_path=policy_path,policy_sha256=policy_sha256,run_metadata_path=run_metadata_path,
            data_root=data_root,artifact_root=artifact_root)
        selection=ev._evidence(metadata,'selection_path','selection_sha256',artifact_root)
        if (selection.get('identity_policy_sha256') != identity_policy_sha256
                or ev._utc(identity_policy['frozen_utc']) > ev._utc(metadata['test_inference_started_utc'])):
            raise ValueError('identity policy not frozen in selection before test inference')
        measurement_class=legacy['measurement_class']
    elif split == 'validation':
        ev.validate_manifest(rows,data_root,split_policy)
        _validate_development_run(metadata,rows,predictions,artifact_root,bindings)
        legacy=ev.score_predictions([r for r in rows if r['split']==split],predictions)
        measurement_class='development_validation'
    else:
        raise ValueError('only validation or complete held-out test runs can be reviewed')
    decisions,review_evidence=validate_identity_reviews(rows=rows,predictions=predictions,
        data_root=data_root,artifact_root=artifact_root,mapping_path=packet_map_path,
        review_paths=identity_review_paths,policy_path=identity_policy_path,
        policy_sha256=identity_policy_sha256,source_bindings=bindings,split=split)
    report=score_reviewed_predictions([r for r in rows if r['split']==split],predictions,decisions)
    report.update(schema_version='beverage-equivalence-evaluation-v1',measurement_class=measurement_class,
        inference_split=split,run_id=metadata['run_id'],run_kind=metadata['run_kind'],
        model_id=metadata['model_id'],adapter_sha256=metadata.get('adapter_sha256'),
        source_evidence=bindings,review_evidence=review_evidence,
        owner_authorization=identity_policy['user_authorization'],
        primary_metric='Full beverage identity equivalent under the frozen owner rubric AND exact positive printed capacity mL; all cases retained.',
        reviewer_kind='Two independently instructed Codex agents; not a human study.',
        provenance_limit='Hashes bind artifact consistency, not factual visual judgments or reviewer independence; isolated recorded review tasks support those attestations. Public photos may have appeared in base pretraining.',
        adapter_target_met=(split=='test' and measurement_class=='measured_adapter'
            and metadata['run_kind']=='adapter' and metadata['dataset_kind']=='real_photos' and report['above_70_percent']),
        generated_utc=datetime.now(timezone.utc).isoformat())
    report['legacy_name_alias_metrics']={k:legacy[k] for k in ('counts','identity','capacity','joint','above_70_percent','cases')}
    return report
