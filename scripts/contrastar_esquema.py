"""Lee catálogo y evalúa fronteras sintéticas mediante SELECT; no inserta datos."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import django

    django.setup()
    from django.db import connection, transaction

    from tests.support.schema import schema_report

    if connection.vendor != "postgresql":
        raise RuntimeError("El contraste requiere PostgreSQL real.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        report = schema_report(connection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "matched": report["matched"],
                "counts": report["counts"],
                "differences": report["differences"],
                "predicates": len(report["predicates"]),
                "probe_cases": sum(p["cases"] for p in report["predicates"]),
                "predicate_mismatches": [p for p in report["predicates"] if p["mismatches"]],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
