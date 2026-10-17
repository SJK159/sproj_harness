// Synthetic seed data for the mock API. Ids match the team's seed exactly.
import type { InstructorSummary, Profile, StudentSummary } from './types';

export const TERM = 'Fall 2026';

export interface CourseDef { course_id: string; title: string; credits: number; prereqs: string[]; offered: boolean }
export interface SectionDef {
  offering_id: string; course_id: string; instructor_id: string;
  capacity: number; enrolled: number; accepts_fe: boolean; fe_slots: number; fe_used: number;
  days: string; start: string; end: string; min_year?: number; min_cgpa?: number;
}

const c = (course_id: string, title: string, prereqs: string[] = [], offered = true, credits = 3): CourseDef =>
  ({ course_id, title, credits, prereqs, offered });

export const COURSES: Record<string, CourseDef> = Object.fromEntries([
  c('CS100', 'Computational Problem Solving', [], false),
  c('CS200', 'Data Structures', ['CS100'], false),
  c('CS300', 'Advanced Programming', ['CS200']),
  c('CS310', 'Algorithms', ['CS200']),
  c('CS360', 'Operating Systems', ['CS200']),
  c('CS370', 'Software Engineering', ['CS200']),
  c('CS381', 'Senior Seminar in Computing'),
  c('CS412', 'Machine Learning', ['CS310']),
  c('CS471', 'Computer Vision', ['CS310']),
  c('CS582', 'Advanced Machine Learning'),
  c('CS999', 'Special Topics in Computing', [], false),
  c('MATH101', 'Calculus I', [], false),
  c('MATH120', 'Linear Algebra'),
  c('GEN101', 'Academic Writing'),
  c('GEN110', 'Ethics and Society'),
  c('GEN120', 'Introduction to Sociology'),
  c('GEN130', 'Public Speaking'),
  c('GEN140', 'Physical Education', [], true, 2),
  c('GEN150', 'Environmental Science'),
].map((x) => [x.course_id, x]));

const s = (
  offering_id: string, instructor_id: string, days: string, start: string, end: string,
  o: Partial<SectionDef> = {},
): SectionDef => ({
  offering_id, course_id: offering_id.split('-')[0], instructor_id, days, start, end,
  capacity: 40, enrolled: 40, accepts_fe: true, fe_slots: 2, fe_used: 0, ...o,
});
const open = { capacity: 60, enrolled: 48 };

export const SECTIONS: SectionDef[] = [
  s('CS412-S1', 'I1', 'MW', '11:00', '12:15', { fe_slots: 3, fe_used: 1 }),
  s('CS412-S2', 'I1', 'TR', '14:00', '15:15', { capacity: 40, enrolled: 35 }),
  s('CS360-S1', 'I1', 'TR', '09:30', '10:45', { fe_slots: 1 }),
  s('CS300-S1', 'I2', 'MW', '09:30', '10:45', open),
  s('CS370-S1', 'I2', 'MW', '14:00', '15:15', { accepts_fe: false, fe_slots: 0 }),
  s('CS471-S1', 'I2', 'TR', '11:00', '12:15', { fe_slots: 2, fe_used: 2 }),
  s('CS381-S1', 'I3', 'F', '10:00', '12:50', { min_year: 4 }),
  s('MATH120-S1', 'I3', 'MW', '11:00', '12:15'),
  s('CS582-S1', 'I3', 'MW', '15:30', '16:45', { min_cgpa: 3.0 }),
  s('CS310-S1', 'I4', 'TR', '12:30', '13:45', open),
  s('GEN101-S1', 'I4', 'F', '14:00', '15:15', open),
  s('GEN110-S1', 'I4', 'TR', '16:00', '17:15', open),
  s('GEN120-S1', 'I4', 'MW', '08:00', '09:15', open),
  s('GEN130-S1', 'I4', 'F', '08:30', '09:45', open),
  s('GEN140-S1', 'I4', 'F', '16:00', '17:50', open),
  s('GEN150-S1', 'I4', 'TR', '08:00', '09:15', open),
];

interface StudentRow { id: string; name: string; year: number; cgpa: number; hint: string; completed: string[]; enrolled: string[] }
const BASE = ['CS100', 'CS200'];
const STUDENT_ROWS: StudentRow[] = [
  { id: 'S1', name: 'Student One', year: 4, cgpa: 3.4, hint: 'Eligible for CS412-S1 (happy path)', completed: [...BASE, 'CS310', 'MATH101'], enrolled: ['CS300-S1', 'GEN101-S1', 'GEN110-S1', 'GEN120-S1', 'GEN130-S1'] },
  { id: 'S2', name: 'Student Two', year: 3, cgpa: 3.0, hint: 'Missing prerequisite CS310', completed: [...BASE, 'MATH101'], enrolled: ['GEN101-S1'] },
  { id: 'S3', name: 'Student Three', year: 3, cgpa: 3.1, hint: 'Timetable clash with CS412-S1 (MATH120)', completed: [...BASE, 'CS310'], enrolled: ['MATH120-S1'] },
  { id: 'S4', name: 'Student Four', year: 3, cgpa: 3.2, hint: 'CS310 still in progress', completed: [...BASE], enrolled: ['CS310-S1'] },
  { id: 'S5', name: 'Student Five', year: 4, cgpa: 3.3, hint: 'At the 20-credit cap', completed: [...BASE, 'CS310', 'MATH101'], enrolled: ['CS300-S1', 'GEN101-S1', 'GEN110-S1', 'GEN120-S1', 'GEN130-S1', 'GEN140-S1', 'GEN150-S1'] },
  { id: 'S6', name: 'Student Six', year: 3, cgpa: 1.9, hint: 'On probation', completed: [...BASE, 'CS310'], enrolled: ['GEN101-S1'] },
  { id: 'S7', name: 'Student Seven', year: 2, cgpa: 3.2, hint: 'Too junior for CS381 (year 4+)', completed: [...BASE, 'CS310'], enrolled: ['GEN101-S1'] },
  { id: 'S8', name: 'Student Eight', year: 4, cgpa: 3.0, hint: 'Already enrolled in CS412', completed: [...BASE, 'CS310'], enrolled: ['CS412-S2'] },
  { id: 'S9', name: 'Student Nine', year: 4, cgpa: 2.8, hint: "Below CS582's CGPA 3.0 minimum", completed: [...BASE, 'CS310', 'MATH101'], enrolled: ['GEN101-S1'] },
];

export const STUDENTS: StudentSummary[] = STUDENT_ROWS.map((r) => ({ student_id: r.id, name: r.name, hint: r.hint }));

export const INSTRUCTORS: InstructorSummary[] = [
  { instructor_id: 'I1', name: 'Instructor One' },
  { instructor_id: 'I2', name: 'Instructor Two' },
  { instructor_id: 'I3', name: 'Instructor Three' },
  { instructor_id: 'I4', name: 'Instructor Four' },
].map((i) => ({ ...i, sections: SECTIONS.filter((x) => x.instructor_id === i.instructor_id).map((x) => x.offering_id) }));

export function seedProfiles(): Record<string, Profile> {
  return Object.fromEntries(STUDENT_ROWS.map((r) => {
    const enrollments = r.enrolled.map((o) => ({ offering_id: o, course_id: o.split('-')[0] }));
    const credits = enrollments.reduce((n, e) => n + (COURSES[e.course_id]?.credits ?? 3), 0);
    const p: Profile = {
      student_id: r.id, name: r.name, program: 'BS Computer Science', year: r.year, cgpa: r.cgpa,
      on_probation: r.cgpa < 2.0, completed: [...r.completed], enrollments, credits,
    };
    return [r.id, p];
  }));
}
