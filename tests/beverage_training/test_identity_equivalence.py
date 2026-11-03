"""Owner-approved full identity grading keeps exact volume and every failure."""
from __future__ import annotations
import copy
import unittest
from ai.beverage_training.equivalence import score_reviewed_predictions


def reference(name, capacity=250):
    return dict(image_id=name, brand='DemoTea', product='Peach tea', capacity_ml=capacity,
        identity_aliases=['DemoTea Peach tea'], background='natural', drink_family='tea')


def prediction(name, **changes):
    result=dict(image_id=name, outcome='success', brand='DemoTea', product='Peach tea', capacity_ml=250, error=None, latency_ms=1)
    result.update(changes)
    return result


class FullIdentityScoringTests(unittest.TestCase):
    def test_equivalent_names_pass_without_relaxing_volume_or_dropping_failures(self):
        rows=[reference(x) for x in 'abcde']
        preds=[prediction('a',product='Peach tea made with green and black tea leaves'),
            prediction('b',capacity_ml=249),prediction('c',outcome='error',brand=None,product=None,capacity_ml=None,error='failed'),
            prediction('e',brand=None)]
        decisions={x:('full_identity_equivalent','full_identity_equivalent') for x in 'abe'}
        decisions.update(c=('uncertain','uncertain'),d=('uncertain','uncertain'))
        before=copy.deepcopy((rows,preds,decisions))
        report=score_reviewed_predictions(rows,preds,decisions)
        self.assertEqual(report['joint']['total'],5)
        self.assertEqual(report['joint']['correct'],1)
        self.assertEqual(report['identity']['correct'],2)
        self.assertEqual(report['capacity']['correct'],2)
        self.assertEqual(report['counts']['missing'],1)
        self.assertEqual(report['counts']['failed'],1)
        self.assertEqual(report['legacy_name_alias_metrics']['identity']['correct'],1)
        self.assertFalse(report['adapter_target_met'])
        self.assertEqual((rows,preds,decisions),before)

    def test_uncertainty_and_disagreement_fail_even_when_lexical_alias_matches(self):
        rows=[reference(x) for x in 'abc']
        preds=[prediction(x) for x in 'abc']
        choices={'a':('full_identity_equivalent','uncertain'),
            'b':('meaningful_identity_error','full_identity_equivalent'),'c':('uncertain','uncertain')}
        report=score_reviewed_predictions(rows,preds,choices)
        self.assertEqual(report['legacy_name_alias_metrics']['joint']['correct'],3)
        self.assertEqual(report['joint']['correct'],0)
        self.assertEqual(report['review_agreement']['unanimous_equivalent'],0)

    def test_unknown_or_malformed_positive_capacity_cannot_be_promoted(self):
        for value in (None,True,250.0,'250'):
            with self.subTest(value=value):
                r=score_reviewed_predictions([reference('a')],[prediction('a',capacity_ml=value)],
                    {'a':('full_identity_equivalent','full_identity_equivalent')})
                self.assertEqual(r['joint']['correct'],0)
        r=score_reviewed_predictions([reference('a',None)],[prediction('a')],
            {'a':('full_identity_equivalent','full_identity_equivalent')})
        self.assertEqual(r['joint']['correct'],0)

    def test_reviews_require_exact_case_coverage_and_known_verdicts(self):
        for choices in ({},{'b':('uncertain','uncertain')},{'a':('yes','yes')},
                        {'a':('full_identity_equivalent',)}, {'a':('uncertain','uncertain'),'b':('uncertain','uncertain')}):
            with self.subTest(choices=choices),self.assertRaises(ValueError):
                score_reviewed_predictions([reference('a')],[prediction('a')],choices)

    def test_perfect_small_fixture_cannot_claim_trained_model_target(self):
        r=score_reviewed_predictions([reference('a')],[prediction('a')],
            {'a':('full_identity_equivalent','full_identity_equivalent')})
        self.assertTrue(r['above_70_percent'])
        self.assertFalse(r['adapter_target_met'])
        self.assertEqual(r['measurement_class'],'unverified_review_assessment')

if __name__=='__main__':unittest.main()

class BoundReviewTests(unittest.TestCase):
    def setUp(self):
        import tempfile,json,hashlib
        from pathlib import Path
        from datetime import datetime,timezone
        from ai.beverage_training import evaluation as ev
        from ai.beverage_training.identity_packets import prepare_identity_packet,IDENTITY_POLICY_SHA256
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.art=self.root/'artifacts';self.art.mkdir();self.data=self.root/'data';self.data.mkdir()
        self.policy=self.art/'policy.json';self.policy.write_bytes((Path(__file__).resolve().parents[2]/'ai/beverage_training/reports/2026-11-02/identity-equivalence-policy-v1.json').read_bytes())
        self.rows=[reference(x) for x in 'ab'];self.preds=[prediction(x) for x in 'ab']
        for row in self.rows:
            path=self.data/(row['image_id']+'.jpg');path.write_bytes(('synthetic fixture '+row['image_id']).encode())
            row.update(split='validation',image_path=path.name,image_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.bindings=dict(manifest_sha256=ev.manifest_sha256(self.rows),split_policy_sha256='b'*64,predictions_sha256='c'*64,run_metadata_sha256='d'*64)
        self.map=prepare_identity_packet(self.rows,self.preds,split='validation',data_root=self.data,output=self.art/'packet',policy_path=self.policy,source_bindings=self.bindings)
        self.mapping=self.art/'packet/packet-map.json';self.packet=self.art/'packet/packet.json'
        self.reviews=[]
        for judge in ('a','b'):
            doc=dict(schema_version='beverage-identity-review-v1',reviewer_id='fixture-'+judge,reviewer_kind='codex_agent',
                independence_attestation='independent_blind_packet_only',reviewed_utc=datetime.now(timezone.utc).isoformat(),
                packet_sha256=self.map['packet_sha256'],policy_sha256=IDENTITY_POLICY_SHA256,
                cases=[dict(case_id=c['case_id'],verdict='full_identity_equivalent',reason='Matching complete identity in photo.',photo_inspected=True) for c in self.map['cases']])
            path=self.art/('review-'+judge+'.json');path.write_text(json.dumps(doc));self.reviews.append(path)
        self.args=dict(rows=self.rows,predictions=self.preds,data_root=self.data,artifact_root=self.art,
            mapping_path=self.mapping,review_paths=self.reviews,policy_path=self.policy,policy_sha256=IDENTITY_POLICY_SHA256,
            source_bindings=self.bindings,split='validation')

    def tearDown(self):self.temp.cleanup()

    def edit(self,path,change):
        import json
        d=json.loads(path.read_text());change(d);path.write_text(json.dumps(d))

    def validate(self):
        from ai.beverage_training.equivalence import validate_identity_reviews
        return validate_identity_reviews(**self.args)

    def test_complete_two_reviews_bind_exact_photos_predictions_and_policy(self):
        decisions,evidence=self.validate()
        self.assertEqual(set(decisions),{'a','b'})
        self.assertTrue(all(pair==('full_identity_equivalent','full_identity_equivalent') for pair in decisions.values()))
        self.assertEqual(len(evidence['reviews']),2)

    def test_duplicate_reviewer_identity_or_missing_review_cannot_claim_independence(self):
        self.edit(self.reviews[1],lambda d:d.update(reviewer_id='fixture-a'))
        with self.assertRaises(ValueError):self.validate()
        self.args['review_paths']=self.reviews[:1]
        with self.assertRaises(ValueError):self.validate()

    def test_wrong_packet_or_policy_hash_is_rejected(self):
        self.edit(self.reviews[0],lambda d:d.update(packet_sha256='0'*64))
        with self.assertRaises(ValueError):self.validate()

    def test_incomplete_duplicate_foreign_and_uninspected_cases_are_rejected(self):
        import json
        original=self.reviews[0].read_text()
        for change in (lambda d:d['cases'].pop(),lambda d:d['cases'].append(dict(d['cases'][0])),
                lambda d:d['cases'][0].update(case_id='foreign'),lambda d:d['cases'][0].update(photo_inspected=False)):
            self.reviews[0].write_text(original);self.edit(self.reviews[0],change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.validate()

    def test_changed_source_bindings_or_photo_bytes_are_rejected(self):
        self.args['source_bindings']=dict(self.bindings,predictions_sha256='f'*64)
        with self.assertRaises(ValueError):self.validate()
        self.args['source_bindings']=self.bindings
        (self.data/'a.jpg').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.validate()

    def test_modified_reference_cannot_pass_even_if_all_file_hashes_are_rebound(self):
        import json,hashlib
        self.edit(self.packet,lambda d:d['cases'][0]['reference'].update(brand='Wrong brand'))
        digest=hashlib.sha256(self.packet.read_bytes()).hexdigest()
        self.edit(self.mapping,lambda d:d.update(packet_sha256=digest))
        for path in self.reviews:self.edit(path,lambda d:d.update(packet_sha256=digest))
        with self.assertRaises(ValueError):self.validate()

    def test_quantities_or_run_information_cannot_be_injected_into_blind_packet(self):
        import hashlib
        self.edit(self.packet,lambda d:d.update(run_kind='adapter'))
        digest=hashlib.sha256(self.packet.read_bytes()).hexdigest()
        self.edit(self.mapping,lambda d:d.update(packet_sha256=digest))
        for path in self.reviews:self.edit(path,lambda d:d.update(packet_sha256=digest))
        with self.assertRaises(ValueError):self.validate()

    def test_rebound_run_hint_in_blind_identifier_is_rejected(self):
        import hashlib
        self.edit(self.packet,lambda d:d.update(blind_id='trained-adapter-checkpoint-v2'))
        digest=hashlib.sha256(self.packet.read_bytes()).hexdigest()
        self.edit(self.mapping,lambda d:d.update(packet_sha256=digest))
        for path in self.reviews:self.edit(path,lambda d:d.update(packet_sha256=digest))
        with self.assertRaises(ValueError):self.validate()

    def test_rebound_run_hint_in_case_identifier_is_rejected(self):
        import hashlib,json
        old=json.loads(self.mapping.read_text())['cases'][0]['case_id']
        def change_case(d):
            for c in d['cases']:
                if c['case_id']==old:c['case_id']='adapter-run-checkpoint-7'
        self.edit(self.packet,change_case);self.edit(self.mapping,change_case)
        digest=hashlib.sha256(self.packet.read_bytes()).hexdigest()
        self.edit(self.mapping,lambda d:d.update(packet_sha256=digest))
        for path in self.reviews:
            self.edit(path,change_case);self.edit(path,lambda d:d.update(packet_sha256=digest))
        with self.assertRaises(ValueError):self.validate()

    def test_reviews_must_postdate_packet_and_not_claim_a_human_study(self):
        self.edit(self.reviews[0],lambda d:d.update(reviewed_utc='2020-01-01T00:00:00Z'))
        with self.assertRaises(ValueError):self.validate()

    def test_symlinked_review_and_traversing_packet_path_are_rejected(self):
        link=self.art/'linked-review.json';link.symlink_to(self.reviews[0]);self.args['review_paths']=[link,self.reviews[1]]
        with self.assertRaises(ValueError):self.validate()
        self.args['review_paths']=self.reviews
        self.edit(self.mapping,lambda d:d.update(packet_path='../review-a.json'))
        with self.assertRaises(ValueError):self.validate()

class CompleteEquivalenceGateTests(unittest.TestCase):
    def setUp(self):
        import importlib.util,json,hashlib
        from pathlib import Path
        from datetime import datetime,timezone
        from ai.beverage_training import evaluation as ev
        from ai.beverage_training.identity_packets import prepare_identity_packet,IDENTITY_POLICY_SHA256
        spec=importlib.util.spec_from_file_location('equivalence_provenance_fixture',Path(__file__).with_name('test_beverage_evaluation.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.fixture=module.ProvenanceTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.args,self.metadata=self.fixture.prepare_run()
        self.root=self.fixture.root
        selection_path=self.root/self.metadata['selection_path']
        selection=json.loads(selection_path.read_text());selection['identity_policy_sha256']=IDENTITY_POLICY_SHA256
        selection_path.write_text(json.dumps(selection));self.metadata['selection_sha256']=ev.file_sha256(selection_path)
        self.metadata['test_inference_started_utc']='2026-11-03T03:00:00Z'
        self.args['run_metadata_path'].write_text(json.dumps(self.metadata))
        self.identity_policy=self.root/'identity-policy.json'
        self.identity_policy.write_bytes((Path(__file__).resolve().parents[2]/'ai/beverage_training/reports/2026-11-02/identity-equivalence-policy-v1.json').read_bytes())
        preds=ev.read_jsonl(self.args['predictions_path'])
        bindings=dict(manifest_sha256=ev.manifest_sha256(self.fixture.rows),split_policy_sha256=self.args['policy_sha256'],
            predictions_sha256=ev.file_sha256(self.args['predictions_path']),run_metadata_sha256=ev.file_sha256(self.args['run_metadata_path']))
        mapping=prepare_identity_packet(self.fixture.rows,preds,split='test',data_root=self.root,output=self.root/'review-packet',policy_path=self.identity_policy,source_bindings=bindings)
        self.reviews=[]
        for judge in 'ab':
            doc=dict(schema_version='beverage-identity-review-v1',reviewer_id='fixture-'+judge,reviewer_kind='codex_agent',
                independence_attestation='independent_blind_packet_only',reviewed_utc=datetime.now(timezone.utc).isoformat(),
                packet_sha256=mapping['packet_sha256'],policy_sha256=IDENTITY_POLICY_SHA256,
                cases=[dict(case_id=c['case_id'],verdict='full_identity_equivalent',reason='Matching complete identity in synthetic fixture.',photo_inspected=True) for c in mapping['cases']])
            path=self.root/('identity-review-'+judge+'.json');path.write_text(json.dumps(doc));self.reviews.append(path)
        self.kwargs=dict(self.args,identity_policy_path=self.identity_policy,identity_policy_sha256=IDENTITY_POLICY_SHA256,
            packet_map_path=self.root/'review-packet/packet-map.json',identity_review_paths=self.reviews)

    def evaluate(self):
        from ai.beverage_training.equivalence import evaluate_equivalence_files
        return evaluate_equivalence_files(**self.kwargs)

    def test_complete_perfect_fixture_keeps_75_cases_and_cannot_satisfy_adapter_goal(self):
        result=self.evaluate()
        self.assertEqual(result['joint']['correct'],75)
        self.assertEqual(result['joint']['total'],75)
        self.assertEqual(result['measurement_class'],'synthetic_fixture')
        self.assertEqual(result['legacy_name_alias_metrics']['joint']['correct'],75)
        self.assertFalse(result['adapter_target_met'])

    def test_final_report_still_rejects_original_inference_provenance_tampering(self):
        import json
        runtime=self.root/self.metadata['runtime_config_path'];value=json.loads(runtime.read_text())
        value['predictions_sha256']='0'*64;runtime.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.evaluate()

    def test_final_policy_cannot_be_added_after_test_or_removed_from_selection(self):
        import json
        from ai.beverage_training import evaluation as ev
        selection_path=self.root/self.metadata['selection_path'];selected=json.loads(selection_path.read_text())
        selected.pop('identity_policy_sha256');selection_path.write_text(json.dumps(selected))
        self.metadata['selection_sha256']=ev.file_sha256(selection_path)
        self.args['run_metadata_path'].write_text(json.dumps(self.metadata))
        with self.assertRaises(ValueError):self.evaluate()

    def test_cli_refuses_overwrite_and_never_runs_inference(self):
        import subprocess,sys
        from pathlib import Path
        command=[sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/evaluate_beverage_equivalence.py')]
        flags=dict(manifest=self.args['manifest_path'],predictions=self.args['predictions_path'],split_policy=self.args['policy_path'],
            split_policy_sha256=self.args['policy_sha256'],run_metadata=self.args['run_metadata_path'],data_root=self.root,artifact_root=self.root,
            identity_policy=self.identity_policy,identity_policy_sha256=self.kwargs['identity_policy_sha256'],packet_map=self.kwargs['packet_map_path'],output=self.root/'equivalence-report.json')
        for key,value in flags.items():command.extend(['--'+key.replace('_','-'),str(value)])
        for path in self.reviews:command.extend(['--identity-review',str(path)])
        run=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        before=(self.root/'equivalence-report.json').read_bytes()
        rerun=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(rerun.returncode,2)
        self.assertEqual((self.root/'equivalence-report.json').read_bytes(),before)
