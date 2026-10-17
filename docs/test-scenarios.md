# Test scenarios: force enrollment

Seed data: `src/harness/mock_zambeel/seed_data.py` (term `2026FA`). Rule numbers in
`src/harness/mock_zambeel/policy.py` are **placeholders, not LUMS policy**: credit cap 20,
CGPA below 2.0 = probation (no FE), prerequisites must be completed (in progress does not count).

## Eligibility (no LLM): `check_fe_eligibility(conn, student, course, section)`

Implemented in `tests/test_fe_eligibility.py`. `can_submit` = no blocking code and the section is full.

| ID | Request | Blocking | Advisory | can_submit |
|---|---|---|---|---|
| E01 | S1 → CS412-S1 | none | OTHER_SECTION_OPEN (CS412-S2) | yes |
| E02 | S1 → CS412-S2 | none | SEATS_AVAILABLE | no: register normally |
| E03 | S2 → CS412-S1 | PREREQ_MISSING (CS310) | OTHER_SECTION_OPEN | no |
| E04 | S3 → CS412-S1 | CLASH (MATH120, MW 11:00) | OTHER_SECTION_OPEN | no |
| E05 | S4 → CS412-S1 | PREREQ_IN_PROGRESS (CS310) | OTHER_SECTION_OPEN | no |
| E06 | S5 → CS412-S1 | CREDIT_LIMIT (20 + 3 > 20) | OTHER_SECTION_OPEN | no |
| E07 | S6 → CS412-S1 | PROBATION (CGPA 1.9) | OTHER_SECTION_OPEN | no |
| E08 | S7 → CS381-S1 | YEAR_RESTRICTION (year 2, needs 4) | | no |
| E09 | S8 → CS412-S1 | ALREADY_ENROLLED | (none: no suggestions when already enrolled) | no |
| E10 | S9 → CS582-S1 | CGPA_BELOW_MIN (2.8 < 3.0) | | no |
| E11 | S1 → CS370-S1 | FE_NOT_ACCEPTED | | no |
| E12 | S1 → CS471-S1 | FE_CAP_REACHED (2 of 2 used) | | no |
| E13 | S1 → CS999-S1 | NOT_OFFERED | | no |
| E14 | S6 → CS582-S1 | PROBATION, CGPA_BELOW_MIN (all codes, not just the first) | | no |

Also tested: S2 → CS360-S1 is submittable (setup for A2 and A5); unknown student or course raises.
E02-E14 are also run through the agent in the acceptance suite: no case is created and the student is never asked to confirm.

## Approval and execution scenarios

Status after M7: every scenario below is an acceptance test in `tests/test_acceptance_uc01.py` (offline, through the
agent, the clients and the real gates, with audit-gap and unauthorized-write checks after each test). Live runs:
A1, A2, A6, E03 in `tests/test_live_agent.py`. Latest results: `docs/acceptance-report.md`.

Implemented later, in the milestone shown. "Full audit trail" means one `audit_events` row per
state transition: DRAFT → AWAITING_CONFIRMATION → SUBMITTED → AWAITING_APPROVAL → APPROVED →
EXECUTING → COMPLETED (or the branch shown).

### A1. Approve (M5, M7)
- Setup: seeded DB. CS412-S1 full, FE cap 3, 0 used.
- Steps: S1 asks for CS412-S1, confirms; I1 approves.
- Expected: case COMPLETED; one FORCE enrollment for S1 in CS412-S1; `fe_used` 1 of 3; student notified; full audit trail.

### A2. Reject (M5, M7)
- Setup: seeded DB.
- Steps: S2 asks for CS360-S1, confirms; I1 rejects with reason "Section is at room capacity".
- Expected: case REJECTED; no enrollment; `execute_enrollment` never runs; the student sees who decided and the reason (UC-01 alternative flow).

### A3. Wrong approver (M2, M7)
- Setup: an S1 → CS412-S1 case in AWAITING_APPROVAL.
- Steps: I2 (does not own CS412) tries to approve.
- Expected: refused; no token minted; case stays AWAITING_APPROVAL; the refusal is audited.

### A4. Bad token (M2, M5, M7)
- Setup: an S1 → CS412-S1 case approved by I1.
- Steps: run `execute_enrollment` with a token that is (a) expired, (b) already used, (c) tampered with (signature mismatch), (d) minted for another case.
- Expected: each one refused; no enrollment; case flagged for review; audit row records the refusal reason.

### A5. FE cap race (M5, M7)
- Setup: CS360-S1 full, FE cap 1, 0 used. S1 and S2 both eligible (S2 has CS200).
- Steps: both request CS360-S1 and confirm; I1 approves both.
- Expected: the first execution COMPLETES (FORCE, `fe_used` 1 of 1); the second ends FAILED with "all 1 force-enrollment slots are used", and the student is told. The deterministic core is already tested in `tests/test_enroll.py` (`test_cap_is_rechecked_at_execution`).

### A6. Student cancels at confirmation (M5, M7)
- Steps: S1 asks for CS412-S1, then declines at the confirmation prompt.
- Expected: case CANCELLED; never SUBMITTED; no instructor notification; no enrollment.

### A7. Duplicate request (M5, M7)
- Setup: an open S1 → CS412-S1 case (AWAITING_APPROVAL).
- Steps: S1 asks for CS412-S1 again.
- Expected: the existing case and its status are returned; no new case; no second enrollment (NFR-03).

### A8. Parallel cases (M5, M7)
- Steps: S1 opens CS412-S1 and CS582-S1 at once (two threads, `thread_id = case_id`). I1 approves CS412-S1; I3 rejects CS582-S1.
- Expected: CS412-S1 COMPLETED, CS582-S1 REJECTED; each resumes on its own thread; neither affects the other.
- A8b (added in M7): if both are approved, the second execution fails: S1 would reach 21 credits (cap 20). Execution re-checks the student-side rules (credits, clash, prerequisites, probation, year/CGPA, already enrolled, offered) before enrolling.

### A9. Restart while waiting (M5, M7)
- Steps: run A1 until AWAITING_APPROVAL; kill the process; start a new process; I1 approves via `scripts/approve.py`.
- Expected: the same thread resumes from the SQLite checkpoint and the case COMPLETES; one enrollment; audit trail has no gaps or duplicates.

## Extended catalogue (manual testing)

Added 2026-10-18 (`EXTRA_*` in `seed_data.py`). It only adds rows; every scenario above gives the same result. Each line is pinned by `tests/test_extended_catalogue.py`.

| Student | Section | Result | What it shows |
|---|---|---|---|
| S1 | CS330-S1 | can request, OTHER_SECTION_OPEN | FE allowed, another section (CS330-S2) has seats |
| S1 | CS340-S1 / CS340-S2 | FE_CAP_REACHED / can request | two full sections, one out of FE slots |
| S2 | CS350-S1 | PREREQ_MISSING | needs CS310 |
| S4 | CS350-S1 | PREREQ_IN_PROGRESS | taking CS310 |
| S1 | CS391-S1 | CLASH | MW 09:30 = HUM101 |
| S8 | CS432-S1 | PREREQ_IN_PROGRESS | prerequisite chain via CS412 |
| S3 | CS435-S1 | PREREQ_IN_PROGRESS | two prerequisites, one in progress |
| S3 | CS450-S1 | YEAR_RESTRICTION | year 4+ |
| S1 | CS473-S1 | FE_NOT_ACCEPTED | full, no FE |
| S1 / S8 | CS491-S1 | can request / CGPA_BELOW_MIN | year 4 and CGPA 3.3 |
| S5 | CS295-S1 | CREDIT_LIMIT (+ CLASH) | 1 credit over a 20-credit load |
| S1 | EE210-S3 | SEATS_AVAILABLE | register normally (EE210 has 3 sections) |
| S1 / S6 | MATH230-S1 | can request / PROBATION | no prerequisite |
| S1 | MGMT250-S1 | FE_CAP_REACHED | all 3 FE slots used |
| S1 | ECON200-S1 | PREREQ_IN_PROGRESS | taking ECON100 |
| S9 | ECON310-S1 | can request | CGPA 2.8 meets 2.5 |
| S7 | ART150-S1 | can request | year 2 meets year 2+ |

Ask "which courses can I force enroll in?" as any student to see the whole-term scan; S1 can request 18 sections and is blocked from 12.

