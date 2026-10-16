"""Force-enrollment rule numbers and reason codes.

PLACEHOLDERS, NOT LUMS POLICY. Chosen by the team to exercise every rule in tests.
The skill file (M3) cites these with labels such as `FE-1 (placeholder v0.1)`.
"""

CREDIT_CAP = 20  # max credits in a term, including the requested course
PROBATION_CGPA = 2.0  # CGPA below this = probation; a student on probation cannot request FE
# Prerequisites must be completed; a prerequisite in progress this term does not count.

# Blocking codes, in the fixed order check_fe_eligibility reports them.
BLOCKING_CODES = (
    "PREREQ_MISSING",
    "PREREQ_IN_PROGRESS",
    "CLASH",
    "CREDIT_LIMIT",
    "PROBATION",
    "YEAR_RESTRICTION",
    "CGPA_BELOW_MIN",
    "FE_NOT_ACCEPTED",
    "FE_CAP_REACHED",
    "ALREADY_ENROLLED",
    "NOT_OFFERED",
)

# Advisory codes: not failures. SEATS_AVAILABLE means no FE is needed (register normally).
ADVISORY_CODES = (
    "SEATS_AVAILABLE",
    "OTHER_SECTION_OPEN",
)
