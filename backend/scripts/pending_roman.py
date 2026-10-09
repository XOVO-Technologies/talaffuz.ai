"""Print the clips that still need Roman Urdu as JSON (used by the /romanize Claude Code skill).

    python scripts/pending_roman.py [project_id] [--api http://127.0.0.1:8000]

With no project_id it uses the most recent project.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id", nargs="?")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    pid = args.project_id or get(f"{args.api}/api/projects")[0]["id"]
    project = get(f"{args.api}/api/projects/{pid}")
    todo = [
        {"id": c["id"], "urdu": c["urdu"]}
        for c in sorted(project["clips"], key=lambda c: c["order"])
        if c["keep"] and c["status"] == "processed" and c["urdu"].strip() and not c["roman"].strip()
    ]
    print(json.dumps({"project_id": pid, "count": len(todo), "items": todo}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
