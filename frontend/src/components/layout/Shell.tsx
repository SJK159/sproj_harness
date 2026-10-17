import type { ReactNode } from 'react';
import { Menu, PanelLeft, PanelRight } from 'lucide-react';
import { useMediaQuery } from '../../lib/hooks';
import { cn } from '../../lib/format';
import { useApp } from '../../state/AppContext';
import { StatePill } from '../ui/StatePill';
import { CasesPage } from '../cases/CasesPage';
import { Inspector } from '../cases/Inspector';
import { ChatView } from '../chat/ChatView';
import { CaseReview } from '../instructor/CaseReview';
import { InstructorHome } from '../instructor/InstructorHome';
import { Sidebar } from './Sidebar';

export function Shell() {
  const { role, view, reviewCaseId, chatNonce, studentId } = useApp();
  return (
    <div className="flex h-dvh overflow-hidden bg-canvas text-ink">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Header />
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            {role === 'instructor'
              ? reviewCaseId ? <CaseReview key={reviewCaseId} caseId={reviewCaseId} /> : <InstructorHome />
              : view === 'cases' ? <CasesPage /> : <ChatView key={`${studentId}-${chatNonce}`} />}
          </div>
          {role === 'student' && view === 'chat' && <Inspector />}
        </div>
      </main>
    </div>
  );
}

function Header() {
  const app = useApp();
  const isMd = useMediaQuery('(min-width: 768px)');
  const session = app.sessions?.find((s) => s.session_id === app.activeSessionId);
  const showNavBtn = !isMd || !app.sidebarOpen;
  let title: ReactNode = 'New chat';
  if (app.role === 'instructor') title = app.reviewCaseId ? 'Case review' : 'Instructor';
  else if (app.view === 'cases') title = 'All my cases';
  else if (session) title = session.title;
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line/70 px-3">
      {showNavBtn && (
        <button
          type="button"
          onClick={() => (isMd ? app.setSidebarOpen(true) : app.setMobileNavOpen(true))}
          className="rounded-lg p-1.5 text-faint hover:bg-sunk hover:text-ink"
          aria-label="Open sidebar"
        >
          {isMd ? <PanelLeft className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <h1 className="truncate text-[14px] font-medium text-ink">{title}</h1>
        {app.role === 'student' && app.view === 'chat' && session?.case && <StatePill state={session.case.state} size="xs" />}
      </div>
      {app.role === 'student' && app.view === 'chat' && (
        <button
          type="button"
          onClick={() => app.setInspectorOpen(!app.inspectorOpen)}
          aria-pressed={app.inspectorOpen}
          aria-label="Toggle case inspector"
          className={cn('inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] hover:bg-sunk', app.inspectorOpen ? 'text-ink' : 'text-faint')}
        >
          <PanelRight className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">Inspector</span>
        </button>
      )}
    </header>
  );
}

