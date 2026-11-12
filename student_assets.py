"""Fetch the private RAG files into runtime storage, never the public repository."""
import hashlib
import json
import os
from pathlib import Path
import re

FILES = {"faiss.index", "chunks.jsonl", "meta.json"}


def prepare_private_rag(data_dir, manifest_path=None, downloader=None):
    manifest_path = Path(manifest_path or Path(__file__).with_name("rag_assets.json"))
    token = os.environ.get("RAG_SOURCE_TOKEN", "")
    if not token:
        raise RuntimeError("Set the private-reference read token in Space Secrets.")
    try:
        manifest = json.loads(manifest_path.read_text())
        if (manifest["repo"] != "your-org/private-reference-space"
                or not re.fullmatch(r"[0-9a-f]{40}", manifest["revision"])
                or set(manifest["files"]) != FILES
                or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in manifest["files"].values())):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("The private reference manifest is invalid.") from None
    root = Path(data_dir) / "references"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    if downloader is None:
        from huggingface_hub import hf_hub_download
        downloader = hf_hub_download
    try:
        for name, expected in manifest["files"].items():
            path = Path(downloader(
                repo_id=manifest["repo"], repo_type="space", revision=manifest["revision"],
                filename="rag_cache/" + name, token=token,
                local_dir=str(root), cache_dir=str(root / ".download-cache"),
            ))
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Reference path escaped private runtime storage")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("Reference checksum mismatch")
            path.chmod(0o600)
    except Exception:
        raise RuntimeError("Private references could not be loaded. Check the read token and pinned files.") from None
    os.environ["RAG_CACHE_DIR"] = str(root / "rag_cache")
    return root / "rag_cache"
