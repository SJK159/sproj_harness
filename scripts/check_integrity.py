"""Check a database for audit gaps (O-03) and enrollments without a verified approval (O-02).

    uv run python scripts/check_integrity.py            # data/harness.db (or HARNESS_DB)
    uv run python scripts/check_integrity.py --db path/to.db
"""

import argparse
import sys
from contextlib import closing
from pathlib import Path

from harness.config import load_env
from harness.integrity import audit_gaps, unauthorized_writes
from harness.mock_zambeel import connect, db_path


def run(path: Path) -> tuple[int, int, list[str]]:
    with closing(connect(path)) as conn:
        cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        enrollments = conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key IS NOT NULL").fetchone()[0]
        return cases, enrollments, audit_gaps(conn) + unauthorized_writes(conn)


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    path = args.db or db_path()
    cases, enrollments, problems = run(path)
    print(f"{path}: {cases} cases, {enrollments} harness enrollments")
    for p in problems:
        print(f"  PROBLEM {p}")
    print("OK: complete audit trails, every enrollment approved" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
