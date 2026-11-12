import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from deploy.package_release import package

ROOT = Path(__file__).resolve().parents[2]


class ReleasePackageTests(unittest.TestCase):
    def test_exact_reviewed_runtime_only(self):
        manifest = ROOT/'deploy/releases/v12-runtime.json'
        entries = json.loads(manifest.read_text())['files']
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'runtime'
            self.assertEqual(package(ROOT, manifest, output), len(entries))
            actual = {str(f.relative_to(output)) for f in output.rglob('*') if f.is_file()}
            self.assertEqual(actual, {e['path'] for e in entries})
            for entry in entries:
                self.assertEqual(hashlib.sha256((output/entry['path']).read_bytes()).hexdigest(), entry['sha256'])
            self.assertFalse(any(name.startswith(('docs/', 'tests/', 'private/', 'deployment-private/')) for name in actual))

    def test_modified_source_or_path_escape_never_creates_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'app.py').write_text('original')
            entry = {'source':'app.py','path':'app.py','sha256':hashlib.sha256(b'original').hexdigest()}
            manifest = root/'manifest.json'; manifest.write_text(json.dumps({'files':[entry]}))
            (root/'app.py').write_text('changed')
            with self.assertRaises(ValueError): package(root, manifest, root/'output')
            self.assertFalse((root/'output').exists())
            (root/'app.py').write_text('original');entry['path']='../escape.py';manifest.write_text(json.dumps({'files':[entry]}))
            with self.assertRaises(ValueError):package(root, manifest, root/'output')
            self.assertFalse((root/'output').exists())

    def test_existing_output_and_linked_sources_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root/'real.py').write_text('original');(root/'app.py').symlink_to(root/'real.py')
            manifest=root/'manifest.json';manifest.write_text(json.dumps({'files':[{'source':'app.py','path':'app.py','sha256':hashlib.sha256(b'original').hexdigest()}]}))
            with self.assertRaises(ValueError):package(root,manifest,root/'output')
            (root/'output').mkdir();(root/'output/keep.txt').write_text('keep')
            with self.assertRaises(ValueError):package(root,manifest,root/'output')
            self.assertEqual((root/'output/keep.txt').read_text(),'keep')
