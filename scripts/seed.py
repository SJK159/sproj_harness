"""Reset and seed the mock Zambeel database (data/harness.db, or HARNESS_DB / --db).

    uv run python scripts/seed.py --reset
"""

import argparse
import sys
from pathlib import Path

from harness.config import load_env
from harness.mock_zambeel import db_path, reset_db, seed

TABLES = [
    "students", "instructors", "courses", "prerequisites", "transcript",
    "offerings", "offering_slots", "enrollments", "cases", "approvals", "audit_events",
]


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the existing DB (all cases and audit rows) first")
    parser.add_argument("--db", type=Path, help="DB path (default: HARNESS_DB or data/harness.db)")
    args = parser.parse_args()

    path = args.db or db_path()
    if path.exists() and not args.reset:
        print(f"{path} already exists. Pass --reset to delete it and reseed.", file=sys.stderr)
        return 1

    conn = reset_db(path)
    seed(conn)
    print(f"seeded {path}")
    for table in TABLES:
        print(f"  {table:<15} {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
