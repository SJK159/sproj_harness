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

## Approval and execution scenarios

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
- Open: if both were approved, S1 would reach 21 credits (cap 20). Execution re-checks only the FE cap, not credits or clashes. Decide whether `enroll` should re-check those too.

### A9. Restart while waiting (M5, M7)
- Steps: run A1 until AWAITING_APPROVAL; kill the process; start a new process; I1 approves via `scripts/approve.py`.
- Expected: the same thread resumes from the SQLite checkpoint and the case COMPLETES; one enrollment; audit trail has no gaps or duplicates.
