import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from student_assets import FILES, prepare_private_rag


class StudentAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "manifest.json"
        self.contents = {name: ("private test content: " + name).encode() for name in FILES}
        self.data = {"repo": "your-org/private-reference-space", "revision": "a" * 40,
                     "files": {n: hashlib.sha256(b).hexdigest() for n, b in self.contents.items()}}
        self.manifest.write_text(json.dumps(self.data))
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def download(self, **kwargs):
        self.calls.append(kwargs)
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.contents[target.name])
        return str(target)

    def test_private_download_is_pinned_checked_and_outside_source(self):
        with patch.dict(os.environ, {"RAG_SOURCE_TOKEN": "test-read-token"}, clear=True):
            result = prepare_private_rag(self.root / "runtime", self.manifest, self.download)
            self.assertEqual(os.environ["RAG_CACHE_DIR"], str(result))
        self.assertEqual(len(self.calls), 3)
        for call in self.calls:
            self.assertEqual(call["revision"], "a" * 40)
            self.assertEqual(call["token"], "test-read-token")
        for name in FILES:
            self.assertEqual((result / name).stat().st_mode & 0o777, 0o600)

    def test_missing_token_and_tampering_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                prepare_private_rag(self.root / "runtime", self.manifest, self.download)
        self.contents["chunks.jsonl"] = b"tampered"
        with patch.dict(os.environ, {"RAG_SOURCE_TOKEN": "NEVER_PRINT_ME"}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                prepare_private_rag(self.root / "runtime", self.manifest, self.download)
            self.assertNotIn("NEVER_PRINT_ME", str(raised.exception))
            self.assertNotIn("RAG_CACHE_DIR", os.environ)

    def test_download_errors_and_manifest_paths_cannot_leak(self):
        def fail(**kwargs):
            raise ValueError("credential=NEVER_PRINT_ME")
        with patch.dict(os.environ, {"RAG_SOURCE_TOKEN": "NEVER_PRINT_ME"}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                prepare_private_rag(self.root / "runtime", self.manifest, fail)
            self.assertNotIn("NEVER_PRINT_ME", str(raised.exception))
            self.data["files"]["../private.txt"] = self.data["files"].pop("meta.json")
            self.manifest.write_text(json.dumps(self.data))
            with self.assertRaises(RuntimeError):
                prepare_private_rag(self.root / "runtime", self.manifest, self.download)
            self.assertFalse(self.calls)
