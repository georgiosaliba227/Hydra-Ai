import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'apply_runtime_patch.py'
spec = importlib.util.spec_from_file_location('patch_helper', SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

class PatchHelperTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        subprocess.run(['git','init','-q'],cwd=root,check=True)
        (root/'Reviewed.swift').write_text('original')
        (root/'Other.swift').write_text('let x = 0')
        subprocess.run(['git','add','.'],cwd=root,check=True)
        subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],cwd=root,check=True)
        return root, {'files': {'Reviewed.swift': {'original_sha256':hashlib.sha256(b'original').hexdigest(), 'patched_sha256':hashlib.sha256(b'patched').hexdigest()}}}

    def test_staged_unrelated_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,evidence=self.fixture(directory)
            (root/'Other.swift').write_text('let x = 1')
            subprocess.run(['git','add','Other.swift'],cwd=root,check=True)
            with self.assertRaises(ValueError): helper.validate_source_tree(root,evidence)

    def test_untracked_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,evidence=self.fixture(directory)
            (root/'Injected.swift').write_text('let x = 1')
            with self.assertRaises(ValueError): helper.validate_source_tree(root,evidence)

    def test_unknown_target_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,evidence=self.fixture(directory)
            self.assertEqual(helper.source_state(root,evidence),'original')
            (root/'Reviewed.swift').write_text('unexpected')
            with self.assertRaises(ValueError): helper.source_state(root,evidence)

if __name__ == '__main__': unittest.main()
