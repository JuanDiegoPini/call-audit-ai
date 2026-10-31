from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def publication_candidates() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def scanner_path() -> str:
    executable = "detect-secrets.exe" if os.name == "nt" else "detect-secrets"
    candidate = Path(sys.executable).with_name(executable)
    return str(candidate) if candidate.exists() else executable


def main() -> int:
    files = publication_candidates()
    result = subprocess.run(
        [scanner_path(), "scan", *files],
        check=True,
        capture_output=True,
        text=True,
    )
    findings = json.loads(result.stdout).get("results", {})
    count = sum(len(items) for items in findings.values())
    print(f"Secret scan findings: {count}")
    return 1 if count else 0


if __name__ == "__main__":
    raise SystemExit(main())
