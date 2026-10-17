import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { InstructorSummary, Notification, Session, StudentSummary } from '../api/types';

export type Role = 'student' | 'instructor';
export type Theme = 'light' | 'dark' | 'system';
export type InspectorTab = 'case' | 'memory' | 'profile';

interface AppState {
  role: Role; setRole: (r: Role) => void;
  studentId: string; setStudentId: (id: string) => void;
  instructorId: string; setInstructorId: (id: string) => void;
  actorId: string;
  students: StudentSummary[] | null; instructors: InstructorSummary[] | null;
  sessions: Session[] | null; refreshSessions: () => Promise<void>; patchSession: (id: string, patch: Partial<Session>) => void;
  activeSessionId: string | null; setActiveSessionId: (id: string | null) => void;
  chatNonce: number;
  openSession: (id: string, opts?: { inspector?: InspectorTab }) => void;
  newChat: () => void;
  view: 'chat' | 'cases'; setView: (v: 'chat' | 'cases') => void;
  reviewCaseId: string | null; setReviewCaseId: (id: string | null) => void;
  notifications: Notification[]; refreshNotifications: () => Promise<void>; pushNotification: (n: Notification) => void; markAllRead: () => void;
  inspectorOpen: boolean; setInspectorOpen: (v: boolean) => void;
  inspectorTab: InspectorTab; setInspectorTab: (t: InspectorTab) => void;
  sidebarOpen: boolean; setSidebarOpen: (v: boolean) => void;
  mobileNavOpen: boolean; setMobileNavOpen: (v: boolean) => void;
  theme: Theme; setTheme: (t: Theme) => void;
  caseVersion: number; bumpCase: () => void;
  memoryVersion: number; bumpMemory: () => void;
  resetDemo: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp outside AppProvider');
  return v;
}

function applyTheme(t: Theme) {
  const dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
}

export function AppProvider({ children, onReset }: { children: ReactNode; onReset: () => void }) {
  const [role, setRoleState] = useState<Role>('student');
  const [studentId, setStudentIdState] = useState('S1');
  const [instructorId, setInstructorIdState] = useState('I1');
  const [students, setStudents] = useState<StudentSummary[] | null>(null);
  const [instructors, setInstructors] = useState<InstructorSummary[] | null>(null);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [chatNonce, setChatNonce] = useState(0);
  const [view, setView] = useState<'chat' | 'cases'>('chat');
  const [reviewCaseId, setReviewCaseId] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.matchMedia('(min-width: 1024px)').matches);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('case');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [theme, setThemeState] = useState<Theme>(() => (localStorage.getItem('fe-theme') as Theme | null) ?? 'system');
  const [caseVersion, setCaseVersion] = useState(0);
  const [memoryVersion, setMemoryVersion] = useState(0);
  const actorId = role === 'student' ? studentId : instructorId;
  const actorRef = useRef(actorId);
  actorRef.current = actorId;

  useEffect(() => {
    void api.listStudents().then(setStudents).catch(() => setStudents([]));
    void api.listInstructors().then(setInstructors).catch(() => setInstructors([]));
  }, []);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem('fe-theme', theme);
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const on = () => applyTheme('system');
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [theme]);

  const refreshSessions = useCallback(async () => {
    if (role !== 'student') return;
    const id = studentId;
    try {
      const s = await api.listSessions(id);
      if (actorRef.current === id) {
        setSessions((prev) => {
          const extra = (prev ?? []).filter((p) => p.title === 'New chat' && !s.some((x) => x.session_id === p.session_id));
          return [...extra, ...s];
        });
      }
    } catch {
      if (actorRef.current === id) setSessions((prev) => prev ?? []);
    }
  }, [role, studentId]);

  const refreshNotifications = useCallback(async () => {
    const id = actorId;
    try {
      const n = await api.listNotifications(id);
      if (actorRef.current === id) setNotifications(n);
    } catch { /* keep previous */ }
  }, [actorId]);

  useEffect(() => {
    setSessions(null);
    setActiveSessionId(null);
    setChatNonce((n) => n + 1);
    setView('chat');
    setReviewCaseId(null);
    setNotifications([]);
    void refreshSessions();
    void refreshNotifications();
  }, [role, studentId, instructorId, refreshSessions, refreshNotifications]);

  const patchSession = useCallback((id: string, patch: Partial<Session>) => {
    setSessions((prev) => prev?.map((s) => (s.session_id === id ? { ...s, ...patch } : s)) ?? prev);
  }, []);

  const closeMobileNav = () => { if (!window.matchMedia('(min-width: 768px)').matches) setMobileNavOpen(false); };

  const openSession = useCallback((id: string, opts?: { inspector?: InspectorTab }) => {
    setActiveSessionId(id);
    setChatNonce((n) => n + 1);
    setView('chat');
    if (opts?.inspector) { setInspectorTab(opts.inspector); setInspectorOpen(true); }
    closeMobileNav();
  }, []);

  const newChat = useCallback(() => {
    setActiveSessionId(null);
    setChatNonce((n) => n + 1);
    setView('chat');
    setInspectorTab('case');
    closeMobileNav();
  }, []);

  const pushNotification = useCallback((n: Notification) => {
    if (n.recipient_id !== actorRef.current) return;
    setNotifications((prev) => (prev.some((p) => p.notification_id === n.notification_id) ? prev : [n, ...prev]));
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      const ids = prev.filter((n) => !n.read_at).map((n) => n.notification_id);
      if (ids.length) void api.markNotificationsRead(ids);
      const ts = new Date().toISOString();
      return prev.map((n) => (n.read_at ? n : { ...n, read_at: ts }));
    });
  }, []);

  const value = useMemo<AppState>(() => ({
    role, setRole: setRoleState, studentId, setStudentId: setStudentIdState, instructorId, setInstructorId: setInstructorIdState, actorId,
    students, instructors, sessions, refreshSessions, patchSession,
    activeSessionId, setActiveSessionId, chatNonce, openSession, newChat,
    view, setView, reviewCaseId, setReviewCaseId: (id) => { setReviewCaseId(id); closeMobileNav(); },
    notifications, refreshNotifications, pushNotification, markAllRead,
    inspectorOpen, setInspectorOpen, inspectorTab, setInspectorTab,
    sidebarOpen, setSidebarOpen, mobileNavOpen, setMobileNavOpen,
    theme, setTheme: setThemeState,
    caseVersion, bumpCase: () => setCaseVersion((v) => v + 1),
    memoryVersion, bumpMemory: () => setMemoryVersion((v) => v + 1),
    resetDemo: () => { api.resetDemo?.(); onReset(); },
  }), [role, studentId, instructorId, actorId, students, instructors, sessions, refreshSessions, patchSession, activeSessionId, chatNonce,
    openSession, newChat, view, reviewCaseId, notifications, refreshNotifications, pushNotification, markAllRead, inspectorOpen, inspectorTab,
    sidebarOpen, mobileNavOpen, theme, caseVersion, memoryVersion, onReset]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
