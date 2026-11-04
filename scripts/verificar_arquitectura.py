"""Comprueba las dependencias de core y propietarios sin configurar Django."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from config.architecture import scan_backend  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=ROOT / "backend")
    args = parser.parse_args()
    try:
        examined, violations = scan_backend(args.backend)
    except (OSError, ValueError) as error:
        parser.exit(2, f"No se pudo examinar la estructura: {type(error).__name__}.\n")
    print(
        json.dumps(
            {"examined": examined, "violations": [asdict(item) for item in violations]},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
