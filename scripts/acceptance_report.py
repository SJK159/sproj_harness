"""Run the UC-01 acceptance tests and write docs/acceptance-report.md.

    uv run python scripts/acceptance_report.py          # offline acceptance suite only
    uv run python scripts/acceptance_report.py --live   # plus the live-model tests (uses Databricks quota)
"""

import argparse
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "docs" / "acceptance-report.md"

SCENARIOS = [  # id, what, BRD mapping, offline test prefix, live test name (or None)
    ("A1", "Approve: check, confirm, approve, execute, notify, remember", "O-01; FR-01..FR-08, FR-10", "test_A1_", "test_a1_live_submit_then_approve"),
    ("A2", "Instructor rejects with a reason", "O-01; FR-05, FR-08", "test_A2_", "test_a2_live_reject"),
    ("A3", "Wrong approver refused; owner then approves", "O-02; FR-05, FR-06", "test_A3_", None),
    ("A4", "Expired / tampered / other-case / reused token", "O-02; FR-06, FR-07, NFR-01", "test_A4_", None),
    ("A5", "FE cap race: second execution fails", "O-02; NFR-03", "test_A5_", None),
    ("A6", "Student declines at confirmation", "O-01; UC-01 step 5", "test_A6_", "test_a6_live_student_declines"),
    ("A7", "Duplicate request returns the open case", "NFR-03", "test_A7_", None),
    ("A8", "Parallel cases resolve independently", "O-01; invariant 6", "test_A8_", None),
    ("A8b", "Both approved: second fails on credit cap at execution", "O-02", "test_A8b_", None),
    ("A9", "Restart while waiting, then approve", "O-01; durable state", "test_A9_", None),
    ("E02-E14", "Ineligible requests through the agent create no case", "FR-04; UC-01 alt. flow", "test_ineligible_", "test_e03_live_ineligible_creates_no_case"),
]


def run_pytest(args: list[str], env: dict[str, str]) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}", *args], cwd=REPO, env=env, check=False)
        results = {}
        for case in ET.parse(xml).getroot().iter("testcase"):
            outcome = "pass"
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "FAIL"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            results[case.get("name")] = outcome
        return results


def summarize(results: dict[str, str], prefix: str) -> str:
    matched = [v for k, v in results.items() if k.startswith(prefix)]
    if not matched:
        return "-"
    passed = matched.count("pass")
    return f"{passed}/{len(matched)} pass" if passed != len(matched) or len(matched) > 1 else "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)

    offline = run_pytest(["tests/test_acceptance_uc01.py", "tests/test_integrity.py"], env)
    live: dict[str, str] = {}
    if args.live:
        live = run_pytest(["-m", "live", "tests/test_live_agent.py", "-k",
                           "a1_live or a2_live or a6_live or e03_live"], {**env, "RUN_LIVE": "1"})

    sys.path.insert(0, str(REPO / "scripts"))
    from check_integrity import run as integrity_run

    from harness.config import load_env
    from harness.mock_zambeel import db_path

    load_env()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "tests", "scripts", "skills", "seed"],
                           cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()
    commit_text = f"`{commit}`" + (" plus uncommitted changes" if dirty else "")
    cases, enrollments, problems = integrity_run(db_path())

    lines = [
        "# UC-01 acceptance report",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} at commit {commit_text} by `scripts/acceptance_report.py`.",
        f"Live model: `{os.environ.get('HARNESS_MODEL', 'unset')}`" + ("" if args.live else " (live tests not run this time)") + ".",
        "",
        "**Offline** runs every scenario through the agent, the student/instructor clients and the real gates with a",
        "scripted model: it proves the guarantees hold whatever the model does. **Live** runs the real model on the main",
        "paths. After every offline test, every case's audit trail is checked for gaps (O-03) and every enrollment for a",
        "verified, owner-issued approval (O-02). Live results are one run per scenario: evidence the paths work,",
        "not a reliability measure (history in docs/decisions.md).",
        "",
        "| Scenario | What | BRD | Offline | Live |",
        "|---|---|---|---|---|",
    ]
    for sid, what, brd, prefix, live_name in SCENARIOS:
        live_cell = live.get(live_name, "-") if live_name else "-"
        lines.append(f"| {sid} | {what} | {brd} | {summarize(offline, prefix)} | {live_cell} |")
    total = len(offline)
    passed = list(offline.values()).count("pass")
    lines += [
        "",
        f"Offline: {passed}/{total} tests passed (acceptance suite + integrity-check self-tests).",
        "",
        "## Objectives",
        "- **O-01** end-to-end workflow against mock Zambeel: A1, A2, A6, A8, A9 (offline and live).",
        "- **O-02** zero unauthorized writes: A3, A4 (4 variants), A5, A8b, plus the `unauthorized_writes` check after every test.",
        "- **O-03** complete, retrievable audit record: the `audit_gaps` check after every test; A9 asserts each transition exactly once.",
        "",
        "## Integrity of the demo database",
        f"`scripts/check_integrity.py` on `{db_path().relative_to(REPO) if db_path().is_relative_to(REPO) else db_path()}`: "
        f"{cases} cases, {enrollments} harness enrollments, "
        + ("no problems." if not problems else f"{len(problems)} problem(s): " + "; ".join(problems)),
        "",
    ]
    REPORT.write_text("\n".join(lines))
    print(f"wrote {REPORT}")
    failed = [k for k, v in {**offline, **live}.items() if v == "FAIL"]
    return 1 if failed or problems else 0


if __name__ == "__main__":
    sys.exit(main())
