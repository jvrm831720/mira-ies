#!/usr/bin/env python3
"""Audit pinned Frappe source refs without network or GitHub Actions minutes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "vendor/frappe/vendor-lock.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-checkout", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(LOCK.read_text(encoding="utf-8"))
    errors = []
    for source in manifest["sources"]:
        path = ROOT / source["path"]
        sha = source["sha"]
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            errors.append("SHA inválido: " + source["key"])
            continue
        if not path.exists():
            if args.require_checkout:
                errors.append("Submódulo não inicializado: " + source["path"])
            else:
                print("SKIP", source["path"], "(use git submodule update --init --recursive)")
            continue
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=False)
        if result.returncode or result.stdout.strip() != sha:
            errors.append("HEAD divergente: " + source["path"])
            continue
        print("OK", source["key"], sha[:12], source["license"])
    for error in errors:
        print("FAIL", error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
