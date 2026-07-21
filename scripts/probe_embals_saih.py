"""Probe embals.es saih-data for aforo stations."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from hidrologia import _fetch_endpoint

def main():
    raw = _fetch_endpoint("saih-data")
    print("type", type(raw).__name__)
    if isinstance(raw, dict):
        print("keys", list(raw.keys()))
        for k, v in raw.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
                if v and isinstance(v[0], dict):
                    print(f"    sample keys: {list(v[0].keys())[:15]}")
                    print(f"    sample: {json.dumps(v[0], ensure_ascii=False)[:300]}")
            else:
                print(f"  {k}: {type(v).__name__}")

if __name__ == "__main__":
    main()
