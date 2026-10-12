"""Verify public MIT-upstream file integrity without accessing private sources."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'docs/upstream-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 'graph-coded-agents.upstream-manifest.v1' or manifest.get('license') != 'MIT':
        print('FAIL: missing MIT upstream manifest contract')
        return 1
    failures = []
    for name, expected in manifest['files'].items():
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or not path.is_file():
            failures.append(name)
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(name)
    print(f'upstream_verified={len(manifest["files"]) - len(failures)}/{len(manifest["files"])} MIT files')
    if failures:
        print('FAIL changed upstream files:', ', '.join(failures))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
