"""Save Roman Urdu back into a project. Reads a JSON object {clip_id: roman} from stdin.

    python scripts/apply_roman.py <project_id> [--api http://127.0.0.1:8000] < roman.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    sys.stdin.reconfigure(encoding="utf-8")
    mapping = json.load(sys.stdin)
    body = json.dumps([{"id": k, "roman": v} for k, v in mapping.items()], ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{args.api}/api/projects/{args.project_id}/clips/bulk?fill_only=true", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.read().decode("utf-8"))


if __name__ == "__main__":
    main()
