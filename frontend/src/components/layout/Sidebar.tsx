import { useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Bell, CheckCircle2, ChevronDown, FlaskConical, LayoutGrid, Monitor, Moon, PanelLeftClose, Plus, RotateCcw, Search, Sun, XCircle,
  AlertTriangle, MessageSquare, Hourglass, Inbox,
} from 'lucide-react';
import type { NotificationKind, Session } from '../../api/types';
import { api } from '../../api/client';
import { cn, relTime } from '../../lib/format';
import { isFinal } from '../../lib/states';
import { useMediaQuery } from '../../lib/hooks';
import { useApp, type Theme } from '../../state/AppContext';
import { Button } from '../ui/Button';
import { Popover } from '../ui/Popover';
import { Segmented } from '../ui/Segmented';
import { SectionLabel, SkeletonList, SyntheticBadge } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';
import { InstructorNav } from '../instructor/InstructorNav';
import { LogoMark } from './LogoMark';

export function Sidebar() {
  const { sidebarOpen, mobileNavOpen, setMobileNavOpen } = useApp();
  const isMd = useMediaQuery('(min-width: 768px)');
  if (isMd) {
    return (
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            key="sidebar"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 272, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="shrink-0 overflow-hidden border-r border-line bg-sunk/50"
            aria-label="Sidebar"
          >
            <div className="h-full w-[272px]"><SidebarBody /></div>
          </motion.aside>
        )}
      </AnimatePresence>
    );
  }
  return (
    <AnimatePresence>
      {mobileNavOpen && (
        <motion.div key="drawer" className="fixed inset-0 z-50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileNavOpen(false)} aria-hidden />
          <motion.aside
            initial={{ x: -290 }}
            animate={{ x: 0 }}
            exit={{ x: -290 }}
            transition={{ type: 'spring', stiffness: 400, damping: 40 }}
            className="absolute inset-y-0 left-0 w-[272px] max-w-[85vw] border-r border-line bg-canvas shadow-xl"
            aria-label="Sidebar"
          >
            <SidebarBody />
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SidebarBody() {
  const { role, setSidebarOpen, setMobileNavOpen } = useApp();
  const isMd = useMediaQuery('(min-width: 768px)');
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-3 pb-2 pt-3">
        <LogoMark size={30} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14.5px] font-semibold leading-tight text-navy">FE Assistant</div>
          <div className="truncate text-[11px] text-faint">LUMS force enrollment</div>
        </div>
        <NotificationsBell />
        <button
          type="button"
          onClick={() => (isMd ? setSidebarOpen(false) : setMobileNavOpen(false))}
          className="rounded-lg p-1.5 text-faint hover:bg-sunk hover:text-ink"
          aria-label="Close sidebar"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>
      <IdentitySwitcher />
      {role === 'student' ? <StudentNav /> : <InstructorNav />}
      <footer className="space-y-2 border-t border-line px-3 py-3">
        <ThemeToggle />
        <div className="flex items-center justify-between gap-2">
          <SyntheticBadge />
          <DemoMenu />
        </div>
      </footer>
    </div>
  );
}

// ---------- identity ----------

function IdentitySwitcher() {
  const { role, setRole, students, instructors, studentId, setStudentId, instructorId, setInstructorId } = useApp();
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const isStudent = role === 'student';
  const cur = isStudent ? students?.find((s) => s.student_id === studentId) : instructors?.find((i) => i.instructor_id === instructorId);
  const curId = isStudent ? studentId : instructorId;
  const sub = isStudent ? (cur && 'hint' in cur ? cur.hint : '') : (cur && 'sections' in cur ? cur.sections.join(', ') : '');
  return (
    <div className="mx-3 mb-3 rounded-xl border border-line bg-surface p-2">
      <div className="px-1 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-faint">Demo: switch user</div>
      <Segmented
        id="role"
        label="Role"
        value={role}
        onChange={(r) => setRole(r)}
        options={[{ value: 'student', label: 'Student' }, { value: 'instructor', label: 'Instructor' }]}
      />
      <button
        ref={btn}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="mt-1.5 flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left hover:bg-sunk"
      >
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-navy/10 font-mono text-[11px] font-semibold text-navy">{curId}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-medium">{cur?.name ?? curId}</span>
          <span className="block truncate text-[11.5px] text-faint">{sub}</span>
        </span>
        <ChevronDown aria-hidden className="h-4 w-4 text-faint" />
      </button>
      <Popover anchor={btn} open={open} onClose={() => setOpen(false)} width={300} label="Choose identity">
        <ul role="listbox" aria-label={isStudent ? 'Students' : 'Instructors'} className="p-1">
          {isStudent
            ? (students ?? []).map((s) => (
              <li key={s.student_id}>
                <button type="button" role="option" aria-selected={s.student_id === studentId}
                  onClick={() => { setStudentId(s.student_id); setOpen(false); }}
                  className={cn('flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-sunk', s.student_id === studentId && 'bg-accent-soft/60')}>
                  <span className="mt-0.5 w-6 shrink-0 font-mono text-[12px] font-semibold text-navy">{s.student_id}</span>
                  <span className="min-w-0"><span className="block text-[13.5px]">{s.name}</span><span className="block text-[12px] text-faint">{s.hint}</span></span>
                </button>
              </li>
            ))
            : (instructors ?? []).map((i) => (
              <li key={i.instructor_id}>
                <button type="button" role="option" aria-selected={i.instructor_id === instructorId}
                  onClick={() => { setInstructorId(i.instructor_id); setOpen(false); }}
                  className={cn('flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-sunk', i.instructor_id === instructorId && 'bg-accent-soft/60')}>
                  <span className="mt-0.5 w-6 shrink-0 font-mono text-[12px] font-semibold text-navy">{i.instructor_id}</span>
                  <span className="min-w-0"><span className="block text-[13.5px]">{i.name}</span><span className="block text-[12px] text-faint">{i.sections.join(', ')}</span></span>
                </button>
              </li>
            ))}
        </ul>
      </Popover>
    </div>
  );
}

// ---------- student nav ----------

function StudentNav() {
  const { sessions, activeSessionId, openSession, newChat, view, setView, setMobileNavOpen } = useApp();
  const [q, setQ] = useState('');
  const filtered = (sessions ?? []).filter((s) => {
    const t = q.trim().toLowerCase();
    return !t || s.title.toLowerCase().includes(t) || s.session_id.toLowerCase().includes(t) || (s.case?.offering_id.toLowerCase().includes(t) ?? false);
  });
  const active = filtered.filter((s) => s.case && !isFinal(s.case.state));
  const past = filtered.filter((s) => s.case && isFinal(s.case.state));
  const chats = filtered.filter((s) => !s.case);
  const groups: Array<[string, Session[]]> = [['Active cases', active], ['Past cases', past], ['Chats', chats]];

  return (
    <>
      <div className="space-y-1.5 px-3 pb-2">
        <Button variant="primary" className="w-full" onClick={newChat}><Plus aria-hidden className="h-4 w-4" /> New chat</Button>
        <button
          type="button"
          onClick={() => { setView('cases'); if (!window.matchMedia('(min-width: 768px)').matches) setMobileNavOpen(false); }}
          aria-current={view === 'cases' ? 'page' : undefined}
          className={cn('flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13.5px] hover:bg-sunk', view === 'cases' ? 'bg-surface font-medium text-ink ring-1 ring-line' : 'text-muted')}
        >
          <LayoutGrid aria-hidden className="h-4 w-4" /> All my cases
        </button>
        <label className="relative block">
          <span className="sr-only">Search sessions</span>
          <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search chats"
            className="h-8 w-full rounded-lg border border-line bg-surface pl-8 pr-2 text-[13px] outline-none placeholder:text-faint focus:border-accent/60"
          />
        </label>
      </div>
      <nav className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="Sessions">
        {sessions === null ? <SkeletonList rows={5} /> : (
          <>
            {groups.map(([label, list]) => list.length > 0 && (
              <div key={label}>
                <SectionLabel>{label}</SectionLabel>
                <ul className="space-y-0.5">
                  <AnimatePresence initial={false}>
                    {list.map((s) => (
                      <motion.li key={s.session_id} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                        <SessionItem s={s} active={view === 'chat' && s.session_id === activeSessionId} onClick={() => openSession(s.session_id)} />
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-6 text-center text-[13px] text-faint">{q ? 'No chats match your search.' : 'No chats yet. Start one above.'}</div>
            )}
          </>
        )}
      </nav>
    </>
  );
}

function SessionItem({ s, active, onClick }: { s: Session; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn('group w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface', active && 'bg-surface ring-1 ring-line')}
    >
      <div className="flex items-center gap-2">
        <span className={cn('min-w-0 flex-1 truncate text-[13.5px]', active ? 'font-medium text-ink' : 'text-ink/90')}>{s.title}</span>
        {s.case && <StatePill state={s.case.state} size="xs" />}
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[11.5px] tabular-nums text-faint">
        <span>{relTime(s.updated_at)}</span>
        {s.case && <span className="hidden truncate font-mono group-hover:inline group-focus-visible:inline">· {s.session_id}</span>}
      </div>
    </button>
  );
}

// ---------- notifications ----------

const KIND_ICON: Record<NotificationKind, { Icon: typeof Bell; cls: string }> = {
  COMPLETED: { Icon: CheckCircle2, cls: 'text-emerald-600 dark:text-emerald-300' },
  REJECTED: { Icon: XCircle, cls: 'text-red-600 dark:text-red-300' },
  FAILED: { Icon: AlertTriangle, cls: 'text-red-600 dark:text-red-300' },
  APPROVAL_REQUESTED: { Icon: Hourglass, cls: 'text-amber-600 dark:text-amber-300' },
  AGENT_MESSAGE: { Icon: MessageSquare, cls: 'text-accent' },
};

function NotificationsBell() {
  const { notifications, markAllRead, role, openSession, setReviewCaseId } = useApp();
  const [open, setOpen] = useState(false);
  const [fresh, setFresh] = useState<number[]>([]);
  const btn = useRef<HTMLButtonElement>(null);
  const unread = notifications.filter((n) => !n.read_at).length;
  const toggle = () => {
    if (!open) { setFresh(notifications.filter((n) => !n.read_at).map((n) => n.notification_id)); markAllRead(); }
    setOpen(!open);
  };
  return (
    <>
      <button ref={btn} type="button" onClick={toggle} aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open}
        className="relative rounded-lg p-1.5 text-faint hover:bg-sunk hover:text-ink">
        <Bell className="h-4 w-4" />
        <AnimatePresence>
          {unread > 0 && (
            <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} transition={{ type: 'spring', stiffness: 400, damping: 22 }}
              className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-semibold tabular-nums text-white">
              {unread}
            </motion.span>
          )}
        </AnimatePresence>
      </button>
      <Popover anchor={btn} open={open} onClose={() => setOpen(false)} width={340} align="end" label="Notifications">
        <div className="border-b border-line px-3.5 py-2.5 text-[13px] font-semibold text-navy">Notifications</div>
        {notifications.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center text-[13px] text-faint"><Inbox className="h-5 w-5" aria-hidden />Nothing yet.</div>
        ) : (
          <ul className="p-1">
            {notifications.map((n) => {
              const k = KIND_ICON[n.kind] ?? KIND_ICON.AGENT_MESSAGE;
              return (
                <li key={n.notification_id}>
                  <button
                    type="button"
                    disabled={!n.case_id}
                    onClick={() => {
                      if (!n.case_id) return;
                      if (role === 'student') openSession(n.case_id, { inspector: 'case' }); else setReviewCaseId(n.case_id);
                      setOpen(false);
                    }}
                    className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-sunk disabled:hover:bg-transparent"
                  >
                    <k.Icon aria-hidden className={cn('mt-0.5 h-4 w-4 shrink-0', k.cls)} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] leading-snug">{n.message}</span>
                      <span className="mt-0.5 block text-[11.5px] tabular-nums text-faint">{n.kind} · {relTime(n.created_at)}</span>
                    </span>
                    {fresh.includes(n.notification_id) && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="New" />}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Popover>
    </>
  );
}

// ---------- footer ----------

function ThemeToggle() {
  const { theme, setTheme } = useApp();
  return (
    <Segmented<Theme>
      id="theme"
      label="Theme"
      value={theme}
      onChange={setTheme}
      options={[
        { value: 'light', label: <Sun className="h-3.5 w-3.5" />, aria: 'Light theme' },
        { value: 'dark', label: <Moon className="h-3.5 w-3.5" />, aria: 'Dark theme' },
        { value: 'system', label: <Monitor className="h-3.5 w-3.5" />, aria: 'System theme' },
      ]}
    />
  );
}

function DemoMenu() {
  const { resetDemo } = useApp();
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={btn} type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] text-faint hover:bg-sunk hover:text-ink">
        <FlaskConical aria-hidden className="h-3.5 w-3.5" /> Demo
      </button>
      <Popover anchor={btn} open={open} onClose={() => setOpen(false)} width={260} align="end" label="Demo menu">
        <div className="p-3">
          <div className="text-[12px] text-faint">API mode: <span className="font-mono text-ink">{api.mode}</span></div>
          {api.resetDemo ? (
            <Button size="sm" className="mt-2.5 w-full" onClick={() => { setOpen(false); resetDemo(); }}>
              <RotateCcw aria-hidden className="h-3.5 w-3.5" /> Reset demo data
            </Button>
          ) : (
            <p className="mt-2 text-[12px] text-faint">Reset is only available with the mock API.</p>
          )}
        </div>
      </Popover>
    </>
  );
}

