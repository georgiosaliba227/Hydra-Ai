#!/usr/bin/env python3
"""Opt-in native UI test against a local synthetic-data backend; never prints tokens."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', default='platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5')
    parser.add_argument('--derived-data', default='/tmp/hydra-e2e-derived')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = os.environ.get('HYDRA_E2E_BACKEND_URL', 'http://127.0.0.1:8000')
    token = os.environ.get('HYDRA_API_TOKEN', '')
    url = urlparse(backend)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1', '::1') or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        parser.error('UI test requires a loopback backend with synthetic data.')
    if len(token) < 32:
        parser.error('Set HYDRA_API_TOKEN to the local development credential (at least 32 characters).')
    # Build does not need the credential; keep it out of build subprocess environment.
    build_env = os.environ.copy()
    build_env.pop('HYDRA_API_TOKEN', None)
    build_env.pop('HYDRA_E2E_API_TOKEN', None)
    derived = Path(args.derived_data).resolve()
    subprocess.run(['xcodebuild', '-project', str(root / 'ios/HydraAI.xcodeproj'),
                    '-scheme', 'HydraAIEndToEnd', '-destination', args.destination,
                    '-derivedDataPath', str(derived), 'CODE_SIGN_IDENTITY=-',
                    'CODE_SIGNING_ALLOWED=YES', 'build-for-testing'], cwd=root, env=build_env, check=True)
    candidates = list((derived / 'Build/Products').glob('HydraAIEndToEnd_*.xctestrun'))
    if len(candidates) != 1:
        raise RuntimeError('Expected exactly one generated UI test run configuration.')
    source = candidates[0]
    data = plistlib.loads(source.read_bytes())
    targets = [data['HydraAIUITests']] if 'HydraAIUITests' in data else [
        target for config in data.get('TestConfigurations', []) for target in config.get('TestTargets', [])
        if target.get('BlueprintName') == 'HydraAIUITests']
    if len(targets) != 1:
        raise RuntimeError('UI test target not found in generated configuration.')
    targets[0].setdefault('EnvironmentVariables', {}).update(
        HYDRA_E2E_BACKEND_URL=backend, HYDRA_E2E_API_TOKEN=token)
    descriptor, private_path = tempfile.mkstemp(prefix='hydra-private-', suffix='.xctestrun', dir=source.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            plistlib.dump(data, handle)
        subprocess.run(['xcodebuild', 'test-without-building', '-xctestrun', private_path,
                        '-destination', args.destination, '-parallel-testing-enabled', 'NO'],
                       cwd=root, env=build_env, check=True)
    finally:
        Path(private_path).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
