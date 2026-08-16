"""Export the OpenAPI schema to packages/contracts/openapi.json.

Server-free and deterministic, so `npm run gen` works without a running API and CI can
diff the result to catch contract drift (`npm run gen:check`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
OUT = REPO_ROOT / "packages" / "contracts" / "openapi.json"

sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> int:
    # Defaults only — the exported contract must not vary with a developer's .env.
    app = create_app(Settings(_env_file=None))
    schema = app.openapi()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Trailing newline + sorted keys so the file is diff-stable across machines.
    OUT.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(REPO_ROOT)} ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
