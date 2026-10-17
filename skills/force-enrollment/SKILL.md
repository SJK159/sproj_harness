---
name: force-enrollment
description: Rules for force enrollment (FE) into a full course section at LUMS, with the rule label to cite for each eligibility check and how to explain results. Read before answering any force-enrollment or eligibility question.
---

# Force enrollment

> **PLACEHOLDER RULES, NOT LUMS POLICY.** Version `placeholder v0.1`, written by the project team to
> exercise every check in tests. Numbers (credit cap 20, probation below CGPA 2.0) are invented.
> Always cite the label of each rule you apply, e.g. "FE-2 (placeholder v0.1)".

Force enrollment means joining a section that is already full, over its capacity, with the instructor's
approval. `check_my_eligibility` returns a code for each rule; the label to cite comes with it.

## Rules

### FE-1 (placeholder v0.1): Force enrollment is for full sections
- `SEATS_AVAILABLE`: the requested section has open seats. No force enrollment is needed: tell the student to register normally.
- `OTHER_SECTION_OPEN`: another section of the same course has seats and fits the student's timetable. Not a failure; mention it as an option.

### FE-2 (placeholder v0.1): Prerequisites must be completed
- `PREREQ_MISSING`: a prerequisite has not been taken.
- `PREREQ_IN_PROGRESS`: a prerequisite is being taken this term. In progress does not count.

### FE-3 (placeholder v0.1): No timetable clash
- `CLASH`: the section overlaps a course the student is already enrolled in this term.

### FE-4 (placeholder v0.1): Credit cap of 20
- `CREDIT_LIMIT`: current credits plus this course would exceed 20.

### FE-5 (placeholder v0.1): No force enrollment on probation
- `PROBATION`: CGPA below 2.0. Students on probation cannot request force enrollment.

### FE-6 (placeholder v0.1): Section restrictions
- `YEAR_RESTRICTION`: the section is limited to a minimum year (e.g. seniors only).
- `CGPA_BELOW_MIN`: the section sets a minimum CGPA the student does not meet.

### FE-7 (placeholder v0.1): The instructor must accept force enrollment, within a cap
- `FE_NOT_ACCEPTED`: the instructor does not accept force enrollment for this section.
- `FE_CAP_REACHED`: all of the section's force-enrollment slots are used.

### FE-8 (placeholder v0.1): One enrollment per course, and only courses offered this term
- `ALREADY_ENROLLED`: the student is already in a section of this course.
- `NOT_OFFERED`: the course or section is not offered this term.

## How to answer
1. Give the verdict first: can request force enrollment, does not need it (seats open), or cannot.
2. List every blocking reason, each with its label in parentheses. Do not stop at the first one.
3. Mention any suggested open section (FE-1) as an option.
4. Keep it short and plain. Do not invent rules that are not listed here.

## Process
1. The student asks for a section that is full and passes every rule above.
2. `submit_case`: the student confirms; a case is created and routed to the section's instructor.
3. `execute_enrollment`: waits for the instructor. On approval the enrollment is made only if the signed
   approval verifies and a force-enrollment slot is still free; otherwise the case ends FAILED with the reason.
4. The student is notified of the outcome (approved and enrolled, rejected with the reason, or failed).
One request per session; a request for the same course while one is open returns the open case.
