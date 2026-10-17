"""Read-only tools for the student agent.

The student is always taken from the runtime context (`runtime.context.student_id`), which the
caller sets per run. No tool has a student_id argument, so the model cannot ask about anyone
else (CLAUDE.md invariant 5). Every tool returns JSON text; failures come back as {"error": ...}.
"""

from contextlib import closing
from typing import Any

from langchain.tools import ToolRuntime, tool

from harness.context import HarnessContext
from harness.mock_zambeel import (
    CURRENT_TERM,
    check_fe_eligibility,
    connect,
    get_section,
    get_student_profile,
)
from harness.mock_zambeel.policy import RULE_LABELS
from harness.tools.common import Refused, run_json, student_id_of


def _codes(codes: tuple[str, ...], reasons: dict[str, str]) -> list[dict[str, str]]:
    return [{"code": c, "rule": RULE_LABELS[c], "reason": reasons[c]} for c in codes]


def _section_row(conn: Any, offering_id: str) -> dict[str, Any]:
    """One section as the student sees it in the timetable: time, seats, force-enrollment terms, restrictions."""
    s = get_section(conn, offering_id)
    slots = conn.execute(
        'SELECT day, start, "end" FROM offering_slots WHERE offering_id = ? ORDER BY start, day', (offering_id,)
    ).fetchall()
    return {
        "offering_id": offering_id,
        "section": s["section"],
        "time": " ".join(f"{r['day']} {r['start']}-{r['end']}" for r in slots),
        "capacity": s["capacity"],
        "available": s["available"],
        "fe_accepted": s["fe_allowed"],
        "fe_slots_left": max(s["fe_cap"] - s["fe_used"], 0) if s["fe_allowed"] else 0,
        "min_year": s["min_year"],
        "min_cgpa": s["min_cgpa"],
    }


def _term_offerings(conn: Any) -> list[Any]:
    return conn.execute(
        """SELECT o.offering_id, o.course_id, o.section, o.instructor_id, c.title, c.credits
           FROM offerings o JOIN courses c ON c.course_id = o.course_id
           WHERE o.term = ? ORDER BY o.course_id, o.section""",
        (CURRENT_TERM,),
    ).fetchall()


@tool
def get_my_profile(runtime: ToolRuntime[HarnessContext]) -> str:
    """Return the signed-in student's profile: year, CGPA, probation status, completed courses,
    current-term enrollments and credits."""
    def go() -> dict[str, Any]:
        with closing(connect()) as conn:
            return get_student_profile(conn, student_id_of(runtime))
    return run_json(go)


@tool
def list_sections(course_id: str, runtime: ToolRuntime[HarnessContext]) -> str:
    """List this term's sections of a course (e.g. course_id="CS412") with time, seats, whether the
    instructor accepts force enrollment, force-enrollment slots left, and any year/CGPA restriction."""
    def go() -> dict[str, Any]:
        student_id_of(runtime)
        with closing(connect()) as conn:
            if conn.execute("SELECT 1 FROM courses WHERE course_id = ?", (course_id,)).fetchone() is None:
                raise Refused(f"No course {course_id!r} in the catalogue.")
            rows = conn.execute(
                "SELECT offering_id FROM offerings WHERE course_id = ? AND term = ? ORDER BY section",
                (course_id, CURRENT_TERM),
            ).fetchall()
            sections = [_section_row(conn, offering_id) for (offering_id,) in rows]
        return {"course_id": course_id, "term": CURRENT_TERM, "sections": sections}
    return run_json(go)


@tool
def check_my_eligibility(course_id: str, section: str, runtime: ToolRuntime[HarnessContext]) -> str:
    """Check whether the signed-in student may request force enrollment in one section
    (e.g. course_id="CS412", section="S1"). Returns every failing rule (blocking), notes such as
    open seats or other open sections (advisory), and the rule label to cite for each."""
    def go() -> dict[str, Any]:
        with closing(connect()) as conn:
            r = check_fe_eligibility(conn, student_id_of(runtime), course_id, section)
        return {
            "request": f"{course_id}-{section}",
            "offering_id": r.offering_id,
            "can_submit": r.can_submit,
            "eligible": r.eligible,
            "fe_needed": r.fe_needed,
            "blocking": _codes(r.blocking, r.reasons),
            "advisory": _codes(r.advisory, r.reasons),
            "suggestions": list(r.suggestions),
        }
    return run_json(go)


@tool
def get_my_cases(runtime: ToolRuntime[HarnessContext]) -> str:
    """List the signed-in student's own force-enrollment cases and their current state."""
    def go() -> dict[str, Any]:
        with closing(connect()) as conn:
            rows = conn.execute(
                """SELECT case_id, offering_id, state, next_action, updated_at FROM cases
                   WHERE student_id = ? ORDER BY created_at""",
                (student_id_of(runtime),),
            ).fetchall()
        return {"cases": [dict(r) for r in rows]}
    return run_json(go)


@tool
def list_offerings(runtime: ToolRuntime[HarnessContext]) -> str:
    """List every course section offered this term: course, title, credits, section, instructor, time, seats left,
    whether it is full, whether the instructor accepts force enrollment, force-enrollment slots left, and any
    year/CGPA restriction. The catalogue is the same for every student; it says nothing about eligibility."""
    def go() -> dict[str, Any]:
        student_id_of(runtime)
        with closing(connect()) as conn:
            sections = []
            for r in _term_offerings(conn):
                row = _section_row(conn, r["offering_id"])
                sections.append({"course_id": r["course_id"], "title": r["title"], "credits": r["credits"],
                                 "instructor_id": r["instructor_id"], **row, "full": row["available"] == 0})
        return {"term": CURRENT_TERM, "sections": sections}
    return run_json(go)


@tool
def scan_my_fe_options(runtime: ToolRuntime[HarnessContext]) -> str:
    """Check the signed-in student against every section offered this term (the same check as
    check_my_eligibility, run on each one) and group the sections: can_request (force enrollment may be requested),
    blocked (every failing rule with its label), register_normally (open seats, no force enrollment needed),
    fe_not_accepted (full, and the instructor takes no force enrollment) and already_enrolled."""
    def go() -> dict[str, Any]:
        student_id = student_id_of(runtime)
        out: dict[str, Any] = {"term": CURRENT_TERM, "can_request": [], "blocked": [], "register_normally": [],
                               "fe_not_accepted": [], "already_enrolled": []}
        with closing(connect()) as conn:
            for r in _term_offerings(conn):
                e = check_fe_eligibility(conn, student_id, r["course_id"], r["section"])
                entry = {"offering_id": r["offering_id"], "title": r["title"]}
                if "ALREADY_ENROLLED" in e.blocking:
                    out["already_enrolled"].append(r["offering_id"])
                elif "FE_NOT_ACCEPTED" in e.blocking:
                    out["fe_not_accepted"].append(r["offering_id"])
                elif e.blocking:
                    out["blocked"].append({**entry, "blocking": _codes(e.blocking, e.reasons)})
                elif e.can_submit:
                    out["can_request"].append({**entry, "advisory": _codes(e.advisory, e.reasons),
                                               "fe_slots_left": _section_row(conn, r["offering_id"])["fe_slots_left"]})
                else:  # eligible, with open seats: no force enrollment needed
                    out["register_normally"].append(r["offering_id"])
        return out
    return run_json(go)


READ_TOOLS = [get_my_profile, list_offerings, list_sections, check_my_eligibility, scan_my_fe_options, get_my_cases]
