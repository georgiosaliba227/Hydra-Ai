#!/usr/bin/env python3
"""Verify public model/source and app artifacts, never app records or credentials.

This is structural/source verification, not a claim of runtime inference quality,
remote GitHub availability, or installation on a physical device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess

DEMO_BUNDLE_ID = 'com.georgiosaliba.hydraai.demo'
PACKAGE_PATH = Path('ios/HydraAI/Resources/HydraBeverage.mlpackage')
REPORT_PATH = Path('ai/on_device/reports/model-v1.json')
NOTICES = ('DINOv2-LICENSE.txt', 'OnDeviceModel-NOTICE.txt')
LFS_PREFIX = b'version https://git-lfs.github.com/spec/v1'


def file_evidence(path: Path) -> dict:
    """Hash nonempty regular files; reject unresolved LFS pointers and symlinks."""
    if path.is_symlink() or not path.is_file():
        raise ValueError('required regular artifact missing')
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        first = stream.read(1024 * 1024)
        if first.startswith(LFS_PREFIX):
            raise ValueError('LFS pointer is not a model artifact')
        block = first
        while block:
            digest.update(block)
            size += len(block)
            block = stream.read(1024 * 1024)
    if size == 0:
        raise ValueError('empty artifact')
    return {'bytes': size, 'sha256': digest.hexdigest()}


def git_output(root: Path, *args: str) -> bytes:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Git HEAD artifact unavailable')
    return result.stdout


def checked_path(root: Path, relative: str | Path) -> Path:
    """Keep fixture/report paths inside their artifact root, without symlinks."""
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('artifact path escapes root')
    path = root / relative
    if any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
        # Resolve the caller root itself before entry; descendants must be plain files.
        raise ValueError('symlink artifact rejected')
    if not path.resolve().is_relative_to(root):
        raise ValueError('artifact path escapes root')
    return path


def verify_head_file(root: Path, path: Path) -> dict:
    """Compare actual Git HEAD blob bytes to the worktree, not just ls-files."""
    evidence = file_evidence(path)
    relative = path.relative_to(root).as_posix()
    blob = git_output(root, 'show', f'HEAD:{relative}')
    if blob.startswith(LFS_PREFIX):
        raise ValueError('Git HEAD contains an LFS pointer')
    if len(blob) != evidence['bytes'] or hashlib.sha256(blob).hexdigest() != evidence['sha256']:
        raise ValueError('worktree artifact differs from Git HEAD')
    return {'path': relative, **evidence,
            'git_blob': git_output(root, 'rev-parse', f'HEAD:{relative}').decode().strip()}


def verify_bundle(*, app: Path, project_root: Path,
                  expected_bundle_id: str = DEMO_BUNDLE_ID,
                  package_path: Path = PACKAGE_PATH, report_path: Path = REPORT_PATH,
                  codesign: bool = False) -> dict:
    """Return credential-free evidence, or raise ValueError on any failed gate.

    Package/report paths are repository-relative. Compiled weights must be byte
    identical to the reviewed package's weights. Signature verification is opt-in
    so unsigned simulator fixtures can be inspected explicitly.
    """
    root = Path(project_root).resolve()
    app = Path(app).resolve()
    report_file = checked_path(root, report_path)
    report_evidence = verify_head_file(root, report_file)
    report = json.loads(report_file.read_text())
    package = checked_path(root, package_path)
    records = report.get('package_files', [])
    if not isinstance(records, list) or not records:
        raise ValueError('model report has no package files')
    names = [row['path'] for row in records]
    required = {'Manifest.json', 'Data/com.apple.CoreML/model.mlmodel',
                'Data/com.apple.CoreML/weights/weight.bin'}
    if len(set(names)) != len(names) or not required.issubset(names):
        raise ValueError('model report omits required package files')
    source_files = []
    for row in records:
        path = checked_path(package, row['path'])
        evidence = verify_head_file(root, path)
        if any(evidence[key] != row[key] for key in ('bytes', 'sha256')):
            raise ValueError('source hash or byte count differs from model report')
        source_files.append(evidence)
    actual_files = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    if actual_files != set(names) or sum(row['bytes'] for row in source_files) != report['package_bytes']:
        raise ValueError('package inventory or total byte count differs from report')
    with checked_path(app, 'Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != expected_bundle_id:
        raise ValueError('unexpected application bundle identifier')
    compiled = checked_path(app, 'HydraBeverage.mlmodelc')
    weights = file_evidence(checked_path(compiled, 'weights/weight.bin'))
    source_weight = next(row for row in records if row['path'].endswith('/weights/weight.bin'))
    if any(weights[key] != source_weight[key] for key in ('bytes', 'sha256')):
        raise ValueError('compiled weights differ from reviewed model')
    graph = file_evidence(checked_path(compiled, 'model.mil'))
    metadata_path = checked_path(compiled, 'metadata.json')
    metadata_evidence = file_evidence(metadata_path)
    metadata = json.loads(metadata_path.read_text())
    if not isinstance(metadata, list) or len(metadata) != 1 or not isinstance(metadata[0], dict):
        raise ValueError('unexpected compiled metadata structure')
    input_schema = metadata[0].get('inputSchema', [])
    output_schema = metadata[0].get('outputSchema', [])
    if (not isinstance(input_schema, list) or not isinstance(output_schema, list)
            or len(input_schema) != 1 or len(output_schema) != 1
            or not isinstance(input_schema[0], dict) or not isinstance(output_schema[0], dict)):
        raise ValueError('unexpected compiled input/output count')
    image, scores = input_schema[0], output_schema[0]
    if (image.get('name') != report['input']['name'] or image.get('type') != 'Image'
            or int(image.get('width', 0)) != report['input']['width']
            or int(image.get('height', 0)) != report['input']['height']
            or scores.get('name') != report['output']['name'] or scores.get('type') != 'MultiArray'
            or json.loads(scores.get('shape', 'null')) != report['output']['shape']):
        raise ValueError('compiled model input/output differs from report')
    user = metadata[0].get('userDefinedMetadata', {})
    if not isinstance(user, dict):
        raise ValueError('unexpected compiled user metadata structure')
    expected = {'hydra.model_id': report['model_id'], 'hydra.base_revision': report['base']['revision'],
                'hydra.manifest_sha256': report['manifest_sha256']}
    if any(user.get(key) != value for key, value in expected.items()):
        raise ValueError('compiled model metadata differs from report')
    if json.loads(user.get('hydra.families', 'null')) != report['families']:
        raise ValueError('compiled model labels differ from report')
    notices = []
    for name in NOTICES:
        source_notice = verify_head_file(root, checked_path(package.parent, name))
        bundled_notice = file_evidence(checked_path(app, name))
        if any(source_notice[key] != bundled_notice[key] for key in ('bytes', 'sha256')):
            raise ValueError('bundled model notice differs from source')
        notices.append({'name': name, **bundled_notice, 'git_blob': source_notice['git_blob']})
    if codesign:
        result = subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], capture_output=True)
        if result.returncode:
            raise ValueError('strict code signature verification failed')
    return {'ok': True, 'verification_version': 'hydra-bundled-model-v1',
            'git_commit': git_output(root, 'rev-parse', 'HEAD').decode().strip(),
            'bundle_identifier': info['CFBundleIdentifier'], 'model_id': report['model_id'],
            'report': report_evidence, 'source_files': source_files,
            'compiled_weights': weights, 'compiled_graph': graph,
            'compiled_metadata': metadata_evidence, 'notices': notices,
            'signature': 'verified_strict' if codesign else 'not_checked'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-bundle-id', default=DEMO_BUNDLE_ID)
    parser.add_argument('--package-path', type=Path, default=PACKAGE_PATH, help='Repository-relative model package')
    parser.add_argument('--report-path', type=Path, default=REPORT_PATH, help='Repository-relative hash report')
    parser.add_argument('--codesign', action='store_true', help='Require codesign --verify --deep --strict')
    args = parser.parse_args()
    try:
        report = verify_bundle(app=args.app, project_root=args.project_root,
                               expected_bundle_id=args.expected_bundle_id,
                               package_path=args.package_path, report_path=args.report_path, codesign=args.codesign)
    except (ValueError, OSError, KeyError, TypeError, plistlib.InvalidFileException):
        # Do not echo untrusted metadata, arbitrary file contents or subprocess output.
        print(json.dumps({'ok': False, 'error': 'bundle_model_verification_failed'}))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
