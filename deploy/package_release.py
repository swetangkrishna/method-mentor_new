"""Copy a hash-verified runtime allowlist into a new directory; never deploy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def package(root, manifest, output):
    root = Path(root).resolve()
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new output directory; existing paths are never overwritten')
    data = json.loads(Path(manifest).read_text())
    validated = []
    targets = set()
    for entry in data['files']:
        source_name, target_name = Path(entry['source']), Path(entry['path'])
        if any(path.is_absolute() or '..' in path.parts for path in (source_name, target_name)):
            raise ValueError('Manifest paths must remain inside the package and source checkout')
        if target_name in targets:
            raise ValueError('Duplicate package target')
        targets.add(target_name)
        source = root / source_name
        if any(part.is_symlink() for part in (source, *source.parents) if part != root and root in part.parents):
            raise ValueError('Symlinked sources are not allowed')
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Release source missing or changed: ' + str(source_name))
        validated.append((source, target_name))
    output.mkdir(parents=True, mode=0o700)
    for source, target in validated:
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return len(validated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--manifest', default=str(Path(__file__).parent/'releases/v12-runtime.json'))
    args = parser.parse_args()
    count = package(Path(__file__).resolve().parents[1], args.manifest, args.output)
    print(f'Prepared {count} hash-verified runtime files. Nothing uploaded or activated.')


if __name__ == '__main__':
    main()
