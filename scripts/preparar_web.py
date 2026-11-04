"""Prepara los artefactos compilados de Entrepares; no necesita credenciales ni Django."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from config.web_build import prepare_frontend  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(prepare_frontend(ROOT / "frontend/dist", ROOT / ".cache/web")))
