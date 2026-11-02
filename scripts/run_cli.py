"""Thin launcher for the src-layout package without installation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirementdelta.cli import main  # noqa: E402

raise SystemExit(main())
