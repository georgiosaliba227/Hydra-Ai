"""Nonbillable tiny bundle/Git fixtures; no device, model runtime or credentials."""
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bundle(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    package = repo / 'ios/HydraAI/Resources/HydraBeverage.mlpackage'
    files = {'Manifest.json': b'{}', 'Data/com.apple.CoreML/model.mlmodel': b'model',
             'Data/com.apple.CoreML/weights/weight.bin': b'fixture-weights'}
    records = []
    for name, data in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    report = repo / 'ai/on_device/reports/model-v1.json'
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({'model_id': 'dinov2-small-beverage-v1',
        'base': {'revision': 'revision'}, 'families': ['water', 'tea'],
        'manifest_sha256': 'a' * 64, 'input': {'name': 'image', 'width': 224, 'height': 224},
        'output': {'name': 'scores', 'shape': [1, 2]}, 'package_files': records,
        'package_bytes': sum(r['bytes'] for r in records)}))
    app = tmp_path / 'HydraAI.app'
    app.mkdir()
    (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.georgiosaliba.hydraai.demo'}))
    compiled = app / 'HydraBeverage.mlmodelc'
    (compiled / 'weights').mkdir(parents=True)
    (compiled / 'weights/weight.bin').write_bytes(files['Data/com.apple.CoreML/weights/weight.bin'])
    (compiled / 'model.mil').write_bytes(b'compiled graph')
    (compiled / 'metadata.json').write_text(json.dumps([{'inputSchema': [{'name': 'image', 'type': 'Image', 'width': '224', 'height': '224'}],
        'outputSchema': [{'name': 'scores', 'type': 'MultiArray', 'shape': '[1, 2]'}], 'userDefinedMetadata': {
        'hydra.model_id': 'dinov2-small-beverage-v1', 'hydra.base_revision': 'revision',
        'hydra.families': json.dumps(['water', 'tea']), 'hydra.manifest_sha256': 'a' * 64}}]))
    for name in ('DINOv2-LICENSE.txt', 'OnDeviceModel-NOTICE.txt'):
        (package.parent / name).write_text('License and provenance fixture\n')
        (app / name).write_bytes((package.parent / name).read_bytes())
    for args in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture']):
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
    return repo, app, package, report


def verify(bundle):
    repo, app, _, _ = bundle
    return load_script('verify_bundled_model').verify_bundle(app=app, project_root=repo)


def test_accepts_matching_source_git_compiled_weight_and_notices(bundle):
    result = verify(bundle)
    assert result['ok'] is True
    assert result['bundle_identifier'] == 'com.georgiosaliba.hydraai.demo'
    assert result['git_commit']
    assert len(result['source_files']) == 3
    assert result['compiled_weights']['bytes'] == len(b'fixture-weights')
    assert result['signature'] == 'not_checked'
    assert 'fixture-weights' not in json.dumps(result)


@pytest.mark.parametrize('fault', ['missing_weight', 'changed_weight', 'source_mismatch', 'git_mismatch',
                                    'wrong_bundle', 'metadata', 'missing_notice', 'changed_notice', 'lfs', 'git_lfs'])
def test_rejects_incomplete_or_mismatched_evidence(bundle, fault):
    repo, app, package, report_path = bundle
    weight = package / 'Data/com.apple.CoreML/weights/weight.bin'
    if fault == 'missing_weight':
        (app / 'HydraBeverage.mlmodelc/weights/weight.bin').unlink()
    elif fault == 'changed_weight':
        (app / 'HydraBeverage.mlmodelc/weights/weight.bin').write_bytes(b'wrong')
    elif fault == 'source_mismatch':
        weight.write_bytes(b'wrong')
    elif fault == 'git_mismatch':
        weight.write_bytes(b'new weights')
        report = json.loads(report_path.read_text())
        row = next(r for r in report['package_files'] if r['path'].endswith('weight.bin'))
        report['package_bytes'] += len(b'new weights') - row['bytes']
        row.update(bytes=len(b'new weights'), sha256=hashlib.sha256(b'new weights').hexdigest())
        report_path.write_text(json.dumps(report))
    elif fault == 'wrong_bundle':
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'production'}))
    elif fault == 'metadata':
        (app / 'HydraBeverage.mlmodelc/metadata.json').write_text('[{"userDefinedMetadata":{}}]')
    elif fault == 'missing_notice':
        (app / 'DINOv2-LICENSE.txt').unlink()
    elif fault == 'changed_notice':
        (app / 'OnDeviceModel-NOTICE.txt').write_text('wrong')
    elif fault in ('lfs', 'git_lfs'):
        weight.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a'*64 + '\nsize 500\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'pointer'], check=True)
        if fault == 'git_lfs':
            weight.write_bytes(b'fixture-weights')  # Smudged worktree cannot hide a pointer in HEAD.
    with pytest.raises(ValueError):
        verify(bundle)


def test_build_command_is_app_only_and_isolated(tmp_path):
    module = load_script('build_iphone_demo')
    command = module.build_command(project_root=ROOT, derived_data=tmp_path / 'Derived Data', team='TEAM123')
    assert command[:3] == ['xcodebuild', '-project', str(ROOT / 'ios/HydraAI.xcodeproj')]
    assert command[command.index('-scheme') + 1] == 'HydraAI'
    assert command[command.index('-destination') + 1] == 'generic/platform=iOS'
    assert command[-1] == 'build'
    for value in ('PRODUCT_BUNDLE_IDENTIFIER=com.georgiosaliba.hydraai.demo',
                  'INFOPLIST_KEY_CFBundleDisplayName=Hydra Demo', 'CODE_SIGN_ENTITLEMENTS=',
                  'DEVELOPMENT_TEAM=TEAM123', 'CODE_SIGN_STYLE=Automatic',
                  'INFOPLIST_KEY_NSCameraUsageDescription=Photograph a drink for on-device analysis. Photos stay on this iPhone.',
                  'INFOPLIST_KEY_NSPhotoLibraryUsageDescription=Select a drink photo for on-device analysis. Photos stay on this iPhone.',
                  'INFOPLIST_KEY_NSLocalNetworkUsageDescription=Connect to your demo backend for requested summaries and questions. Photos, profile details and Apple Health records stay on this iPhone.'):
        assert value in command
    assert not any('PRODUCT_NAME=' in item or item in ('test', 'install') for item in command)


def test_simulator_command_is_unsigned(tmp_path):
    command = load_script('build_iphone_demo').build_command(project_root=ROOT, derived_data=tmp_path, simulator=True)
    assert command[command.index('-destination') + 1] == 'generic/platform=iOS Simulator'
    assert 'CODE_SIGNING_ALLOWED=NO' in command
    assert 'CODE_SIGN_ENTITLEMENTS=' in command
    assert not any(item.startswith('DEVELOPMENT_TEAM=') for item in command)


@pytest.mark.parametrize('schema', ['inputSchema', 'outputSchema'])
def test_rejects_incompatible_model_schema(bundle, schema):
    _, app, _, _ = bundle
    path = app / 'HydraBeverage.mlmodelc/metadata.json'
    metadata = json.loads(path.read_text())
    metadata[0][schema][0]['name'] = 'wrong'
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        verify(bundle)


def test_strict_codesign_failure_rejected(bundle, monkeypatch):
    repo, app, _, _ = bundle
    module = load_script('verify_bundled_model')
    run = subprocess.run
    observed = []

    def reject_signature(command, **kwargs):
        if command[0] == 'codesign':
            observed.append(command)
            return subprocess.CompletedProcess(command, 1, stderr=b'private rejected details')
        return run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, 'run', reject_signature)
    with pytest.raises(ValueError, match='strict code signature verification failed'):
        module.verify_bundle(app=app, project_root=repo, codesign=True)
    assert observed == [['codesign', '--verify', '--deep', '--strict', str(app)]]


def test_cli_rejection_does_not_echo_untrusted_content(bundle):
    repo, app, _, _ = bundle
    (app / 'HydraBeverage.mlmodelc/metadata.json').write_text('PRIVATE_FIXTURE_DO_NOT_ECHO')
    result = subprocess.run([__import__('sys').executable, str(ROOT / 'scripts/verify_bundled_model.py'),
                             '--app', str(app), '--project-root', str(repo)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {'ok': False, 'error': 'bundle_model_verification_failed'}
    assert 'PRIVATE_FIXTURE' not in result.stdout + result.stderr


def test_build_environment_omits_runtime_secrets_without_mutating_parent():
    module = load_script('build_iphone_demo')
    original = {'PATH': '/usr/bin', 'HOME': '/fixture/home', 'HYDRA_TOKEN': 'private',
                'META_API_KEY': 'private', 'MODEL_API_KEY': 'private',
                'DEVICECTL_CHILD_HYDRA_TOKEN': 'private'}
    assert module.build_environment(original) == {'PATH': '/usr/bin', 'HOME': '/fixture/home'}
    assert original['HYDRA_TOKEN'] == 'private'


def test_builder_runs_only_xcodebuild_with_filtered_environment(tmp_path, monkeypatch, capsys):
    module = load_script('build_iphone_demo')
    monkeypatch.setenv('HYDRA_TOKEN', 'PRIVATE_BUILD_SENTINEL')
    monkeypatch.setenv('META_API_KEY', 'PRIVATE_BUILD_SENTINEL')
    monkeypatch.setattr(__import__('sys'), 'argv', ['build_iphone_demo.py', '--derived-data', str(tmp_path), '--simulator'])
    calls = []

    def run_build(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, 'run', run_build)
    assert module.main() == 0
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == 'xcodebuild'
    assert command[-1] == 'build'
    assert 'HYDRA_TOKEN' not in kwargs['env']
    assert 'META_API_KEY' not in kwargs['env']
    output = capsys.readouterr().out
    assert 'PRIVATE_BUILD_SENTINEL' not in output
    report = json.loads(output)
    assert report['executed'] is True
    assert report['returncode'] == 0
    assert report['app'].endswith('/Debug-iphonesimulator/HydraAI.app')


@pytest.mark.parametrize('invalid_user', ['wrong', [], None])
def test_rejects_malformed_user_metadata(bundle, invalid_user):
    _, app, _, _ = bundle
    path = app / 'HydraBeverage.mlmodelc/metadata.json'
    metadata = json.loads(path.read_text())
    metadata[0]['userDefinedMetadata'] = invalid_user
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        verify(bundle)
