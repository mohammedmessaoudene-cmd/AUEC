# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.runtime import UniversalRuntime
from aiew_uc.verification import verify_result

manifest = json.loads((ROOT / "examples" / "hello_manifest.json").read_text(encoding="utf-8"))
result = UniversalRuntime().execute(manifest)
verify_result(result, manifest)
print(json.dumps(result, indent=2, ensure_ascii=False))
