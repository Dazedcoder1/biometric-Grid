"""
Generate the local development KEK and write it into .env.

    python scripts/init_kek.py

Writes KMS_MOCK_KEY if it is absent or empty. Refuses to overwrite an existing
value — rotating the KEK makes every stored payload undecryptable, so that has
to be a deliberate act with a re-encryption pass behind it, not a script rerun.

Development only. In production KMS_PROVIDER=aws and the KEK lives in AWS KMS,
where this script is irrelevant.
"""

from __future__ import annotations

import base64
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import ENV_FILE  # noqa: E402

KEY = "KMS_MOCK_KEY"


def main() -> int:
    if not ENV_FILE.is_file():
        print(f"  No .env found at {ENV_FILE}")
        return 1

    text = ENV_FILE.read_text(encoding="utf-8")
    existing = re.search(rf"^{KEY}\s*=\s*(.*)$", text, flags=re.MULTILINE)

    if existing and existing.group(1).strip().strip('"').strip("'"):
        print(f"\n  {KEY} is already set. Leaving it alone.")
        print("  Changing it makes every stored credential undecryptable —")
        print("  that needs a deliberate re-encryption pass, not this script.\n")
        return 0

    kek = base64.urlsafe_b64encode(os.urandom(32)).decode()

    if existing:
        text = re.sub(
            rf"^{KEY}\s*=.*$", f'{KEY}="{kek}"', text, count=1, flags=re.MULTILINE
        )
    else:
        text = text.rstrip("\n") + (
            "\n\n"
            "# ─── Credential vault: key management ────────────────────────────────────\n"
            "# Local development KEK. Wraps every per-credential data key.\n"
            "#\n"
            "# This sits in the same file as DATABASE_URL, so one file read is total\n"
            "# compromise. Acceptable for development; NOT the production design —\n"
            "# there KMS_PROVIDER=aws and the key never leaves AWS KMS.\n"
            "#\n"
            "# Changing this value makes every stored credential unreadable.\n"
            "KMS_PROVIDER=mock\n"
            "KMS_KEY_ID=local-dev-kek-v1\n"
            f'{KEY}="{kek}"\n'
        )

    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"\n  Wrote {KEY} to {ENV_FILE.name}.")
    print("  Development KEK only. Back it up nowhere; regenerate if lost —")
    print("  and accept that anything already encrypted is then gone.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
