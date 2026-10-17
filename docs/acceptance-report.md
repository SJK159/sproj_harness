# UC-01 acceptance report

Generated 2026-10-17 12:31 UTC at commit `8aeac3e` plus uncommitted changes (the M7 work, committed together with this report) by `scripts/acceptance_report.py`.
Live model: `databricks:databricks-gpt-oss-120b`.

**Offline** runs every scenario through the agent, the student/instructor clients and the real gates with a
scripted model: it proves the guarantees hold whatever the model does. **Live** runs the real model on the main
paths. After every offline test, every case's audit trail is checked for gaps (O-03) and every enrollment for a
verified, owner-issued approval (O-02). Live results are one run per scenario: evidence the paths work,
not a reliability measure (history in docs/decisions.md).

| Scenario | What | BRD | Offline | Live |
|---|---|---|---|---|
| A1 | Approve: check, confirm, approve, execute, notify, remember | O-01; FR-01..FR-08, FR-10 | pass | pass |
| A2 | Instructor rejects with a reason | O-01; FR-05, FR-08 | pass | pass |
| A3 | Wrong approver refused; owner then approves | O-02; FR-05, FR-06 | pass | - |
| A4 | Expired / tampered / other-case / reused token | O-02; FR-06, FR-07, NFR-01 | 4/4 pass | - |
| A5 | FE cap race: second execution fails | O-02; NFR-03 | pass | - |
| A6 | Student declines at confirmation | O-01; UC-01 step 5 | pass | pass |
| A7 | Duplicate request returns the open case | NFR-03 | pass | - |
| A8 | Parallel cases resolve independently | O-01; invariant 6 | pass | - |
| A8b | Both approved: second fails on credit cap at execution | O-02 | pass | - |
| A9 | Restart while waiting, then approve | O-01; durable state | pass | - |
| E02-E14 | Ineligible requests through the agent create no case | FR-04; UC-01 alt. flow | 13/13 pass | pass |

Offline: 29/29 tests passed (acceptance suite + integrity-check self-tests).

## Objectives
- **O-01** end-to-end workflow against mock Zambeel: A1, A2, A6, A8, A9 (offline and live).
- **O-02** zero unauthorized writes: A3, A4 (4 variants), A5, A8b, plus the `unauthorized_writes` check after every test.
- **O-03** complete, retrievable audit record: the `audit_gaps` check after every test; A9 asserts each transition exactly once.

## Integrity of the demo database
`scripts/check_integrity.py` on `data/harness.db`: 1 cases, 1 harness enrollments, no problems.
