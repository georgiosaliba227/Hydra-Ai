#!/usr/bin/env python3
"""Build the isolated Hydra Demo app. Never install, launch or provision a token.

The app product remains HydraAI.app. Simulator builds use ad hoc signing for
Keychain persistence. Use --dry-run to inspect the exact command;
xcodebuild output goes to a build log, not an environment/credential dump.
"""
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
import subprocess


def build_command(*, project_root: Path, derived_data: Path,
                  team: str | None = None, simulator: bool = False) -> list[str]:
    """Construct the existing app scheme's Debug build without test-ID overrides."""
    if team is not None and (not team.isalnum() or not team.isascii()):
        raise ValueError('team must be an alphanumeric Apple development team identifier')
    destination = 'generic/platform=iOS Simulator' if simulator else 'generic/platform=iOS'
    command = ['xcodebuild', '-project', str(Path(project_root).resolve() / 'ios/HydraAI.xcodeproj'),
               '-scheme', 'HydraAI', '-configuration', 'Debug', '-destination', destination,
               '-derivedDataPath', str(Path(derived_data).resolve()),
               'PRODUCT_BUNDLE_IDENTIFIER=com.georgiosaliba.hydraai.demo',
               'INFOPLIST_KEY_CFBundleDisplayName=Hydra Demo', 'CODE_SIGN_ENTITLEMENTS=',
               'INFOPLIST_KEY_NSCameraUsageDescription=Photograph a drink for on-device analysis. Photos stay on this iPhone.',
               'INFOPLIST_KEY_NSPhotoLibraryUsageDescription=Select a drink photo for on-device analysis. Photos stay on this iPhone.',
               'INFOPLIST_KEY_NSLocalNetworkUsageDescription=Connect to your demo backend for requested summaries and questions. Photos, profile details and Apple Health records stay on this iPhone.']
    if simulator:
        command.extend(['CODE_SIGN_IDENTITY=-', 'CODE_SIGNING_ALLOWED=YES', 'ONLY_ACTIVE_ARCH=YES'])
    elif team:
        command.extend([f'DEVELOPMENT_TEAM={team}', 'CODE_SIGN_STYLE=Automatic'])
    command.append('build')
    return command


def build_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Exclude runtime secrets from Xcode's child environment without logging them."""
    source = os.environ if environment is None else environment
    return {key: value for key, value in source.items()
            if not key.startswith(('HYDRA_', 'META_', 'DEVICECTL_CHILD_')) and key != 'MODEL_API_KEY'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--derived-data', type=Path, required=True)
    parser.add_argument('--team', help='Apple development team ID for automatic signing')
    parser.add_argument('--simulator', action='store_true', help='Ad hoc signed generic simulator build with Keychain support')
    parser.add_argument('--dry-run', action='store_true', help='Print command JSON without running Xcode')
    parser.add_argument('--log-file', type=Path, help='Default: DerivedData/hydra-demo-build.log')
    args = parser.parse_args()
    try:
        command = build_command(project_root=args.project_root, derived_data=args.derived_data,
                                team=args.team, simulator=args.simulator)
        platform = 'iphonesimulator' if args.simulator else 'iphoneos'
        product = args.derived_data.resolve() / f'Build/Products/Debug-{platform}/HydraAI.app'
        report = {'command': command, 'app': str(product), 'executed': False}
        if args.dry_run:
            print(json.dumps(report, indent=2))
            return 0
        log_file = args.log_file or args.derived_data / 'hydra-demo-build.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=build_environment())
        report.update(executed=True, returncode=result.returncode, log_file=str(log_file.resolve()))
        print(json.dumps(report, indent=2))
        return 0 if result.returncode == 0 else 1
    except (OSError, ValueError):
        print(json.dumps({'ok': False, 'error': 'demo_build_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
