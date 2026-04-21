#!/usr/bin/env python3
"""Standalone Adjutant installer entrypoint.

This thin wrapper exists at the repository root so a freshly downloaded release
tarball can be installed with:

    python3 install.py

without requiring an editable install first.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from adjutant.setup.install import main as installer_main

    installer_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
