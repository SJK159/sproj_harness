"""Build the 19 November meeting PDFs from reviewed, explicitly authored content.

Run with a Python environment containing reportlab. This does not inspect private
configuration or execute the agent. Snapshot: ammar/fa933cc; nausher/e7e3ad6.
"""
from pathlib import Path
import math

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)
FONT = Path('C:/Windows/Fonts')
for name, filename in [('UI','segoeui.ttf'),('UI-Bold','segoeuib.ttf'),('UI-Italic','segoeuii.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONT / filename)))
pdfmetrics.registerFontFamily('UI',normal='UI',bold='UI-Bold',italic='UI-Italic',boldItalic='UI-Bold')
INK = colors.HexColor('#152C46')
TEAL = colors.HexColor('#087F83')
BLUE = colors.HexColor('#EAF1F8')
PALE = colors.HexColor('#E8F5F2')
MUTED = colors.HexColor('#4C6074')
LINE = colors.HexColor('#D5DFE7')
AMBER = colors.HexColor('#FFF1D7')
WHITE = colors.white


def style(size=10.4, color=INK, leading=None, bold=False):
    return ParagraphStyle('p',fontName='UI-Bold' if bold else 'UI',fontSize=size,
                          leading=leading or size*1.36,textColor=color,spaceAfter=0)


def pdraw(c,text,x,top,width,size=10.4,color=INK,bold=False):
    p = Paragraph(text,style(size,color,bold=bold))
    _, h = p.wrap(width,1000)
    p.drawOn(c,x,top-h)
    return h


class Page:
    def __init__(self,c,number,title,subtitle):
        self.c,self.n,self.w,self.h = c,number,595.28,841.89
        c.setFillColor(TEAL);c.rect(0,self.h-8,self.w,8,fill=1,stroke=0)
        pdraw(c,'LUMS PROCESS ORCHESTRATOR  /  MEETING GUIDE',42,810,510,8,TEAL,True)
        self.y=776
        self.y-=pdraw(c,title,42,self.y,511,25,bold=True)+8
        self.y-=pdraw(c,subtitle,42,self.y,511,10.2,MUTED)+17
    def body(self,text):
        self.y-=pdraw(self.c,text,42,self.y,511)+9
    def heading(self,text):
        self.y-=pdraw(self.c,text,42,self.y,511,12,TEAL,True)+7
    def callout(self,text,fill=PALE):
        p=Paragraph(text,style(10.3));_,h=p.wrap(487,1000)
        self.c.setFillColor(fill);self.c.roundRect(42,self.y-h-20,511,h+20,7,fill=1,stroke=0)
        p.drawOn(self.c,54,self.y-h-10);self.y-=h+31
    def table(self,headers,rows,widths=None,size=9.2,padding=7):
        widths=widths or [511/len(headers)]*len(headers)
        data=[[Paragraph(str(v),style(size,WHITE,bold=True)) for v in headers]]
        data += [[Paragraph(str(v),style(size)) for v in row] for row in rows]
        t=Table(data,colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
            ('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,BLUE]),
            ('LINEBELOW',(0,0),(-1,-1),0.35,LINE)]))
        _,h=t.wrap(511,1000);t.drawOn(self.c,42,self.y-h);self.y-=h+12
    def end(self):
        if self.y < 49: raise RuntimeError(f'Guide page {self.n} overflows: {self.y}')
        self.c.setStrokeColor(LINE);self.c.line(42,42,553,42)
        pdraw(self.c,'19 NOV 2026  |  ammar fa933cc  |  Synthetic academics; live acceptance pending',42,31,470,7.5,MUTED)
        pdraw(self.c,str(self.n),535,31,20,8,MUTED)
        self.c.showPage()


def arrow(c,x1,y1,x2,y2,color=TEAL,dashed=False):
    c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.6)
    c.setDash(4,3) if dashed else c.setDash()
    c.line(x1,y1,x2,y2);c.setDash()
    a=math.atan2(y2-y1,x2-x1);l=7
    path=c.beginPath();path.moveTo(x2,y2)
    path.lineTo(x2-l*math.cos(a-.42),y2-l*math.sin(a-.42))
    path.lineTo(x2-l*math.cos(a+.42),y2-l*math.sin(a+.42));path.close()
    c.drawPath(path,fill=1,stroke=0)


def box(c,x,y,w,h,title,body='',fill=BLUE,title_size=12,body_size=9):
    c.setFillColor(fill);c.setStrokeColor(LINE);c.roundRect(x,y,w,h,8,fill=1,stroke=1)
    top=y+h-11
    used=pdraw(c,title,x+11,top,w-22,title_size,bold=True)
    if body:
        used+=5+pdraw(c,body,x+11,top-used-5,w-22,body_size,MUTED)
    if used > h-20: raise RuntimeError(f'Box overflow: {title}: {used} > {h-20}')


def guide():
    c=canvas.Canvas(str(OUT/'SProj_Repo_Defence_Guide.pdf'),pagesize=(595.28,841.89))
    c.setTitle('LUMS Process Orchestrator | Repository and Defence Guide')
    c.setAuthor('SProj Group 4 | Ammar - Agent and Orchestrator')
    p=Page(c,1,'The project in one picture','What we built, what each part does, and whose work you are presenting.')
    p.callout('<b>Your opening:</b> We built a force-enrollment assistant that plans and explains, but deterministic services control every academic write. Verified identity follows the user; saved approvals and jobs let work continue when the student goes offline.')
    p.body('<b>Force enrollment</b> means joining a full section with its owning instructor\'s approval. This repository is a <b>harness</b>: the tools, rules, state, identity and human controls around a language model. It currently uses a synthetic Zambeel academic simulator, not LUMS production systems.')
    y=p.y-195
    box(c,42,y+130,138,61,'React browser','Chat, case view, confirmation',title_size=11)
    box(c,207,y+130,164,61,'FastAPI + agent','Login/session, planning, HITL',title_size=11)
    box(c,398,y+130,155,61,'Microsoft Entra','Project identity provider',title_size=11)
    arrow(c,180,y+160,207,y+160);arrow(c,371,y+160,398,y+160)
    box(c,207,y+47,164,61,'FE MCP','Case, approval, execution',fill=PALE,title_size=11)
    box(c,398,y+47,155,61,'Zambeel MCP','Academic reads and enrollment',title_size=11)
    box(c,42,y+47,138,61,'Durable worker','App token + case ID',fill=PALE,title_size=11)
    arrow(c,289,y+130,289,y+108);arrow(c,180,y+77,207,y+77);arrow(c,371,y+77,398,y+77)
    arrow(c,352,y+130,449,y+108,dashed=True)
    pdraw(c,'Shared persistent SQLite: cases / academics / approvals / audit / jobs',42,y+25,511,9,MUTED)
    p.y=y-9
    p.heading('Three contributions, kept distinct')
    p.table(['Existing team baseline','Ammar - your role','Nausherwan - integrated'],[
        ['Deep agent, eligibility subagent, FE rules, HITL, audit, checkpoints/memory, UI and local MCPs.',
         'BFF login/cache, verified identity, per-resource MCP client, UI auth, durable jobs/worker and terminal reconciliation.',
         'MCP JWT/role validation, FE app calls to Zambeel, worker-only endpoint, atomic approval/job and FE recovery.']],size=9.1)
    p.body('<b>Snapshot:</b> origin/ammar = fa933cc; origin/nausher = e7e3ad6, integrated into ammar. Main remains 8e234b8. Code was already pushed before preparing this guide. Oracle/revsoft.net is the later hosting plan; Azure references in the October plan are historical.')
    p.end()

    p=Page(c,2,'How to read the repository','Follow responsibilities and one request, rather than memorising every line.')
    p.table(['Area / files','What to understand'],[
        ['src/harness/agent.py<br/>subagents.py; tools/; skills/','Builds create_deep_agent; plans with write_todos; reads the FE skill; delegates academic checking. Main agent owns write tools. Subagent returns a compact structured EligibilityVerdict.'],
        ['workflow.py; cases.py<br/>approvals.py; audit.py','Deterministic workflow and allowed state transitions. Instructor ownership, approval signing/consume-once, execution checks and transition audit. These decide whether writes are allowed.'],
        ['mock_zambeel/; academic.py','Synthetic academics, seed data and FE policy. Academic adapter lets FE use remote MCP operations while preserving workflow logic.'],
        ['api/; frontend/src/','FastAPI routes/auth/SSE; React screens, account gate, CSRF requests, chat and case display. api/events.py translates graph updates into UI events.'],
        ['mcp/','FastMCP FE/Zambeel servers; client.py/authenticated.py send calls; entra.py validates receiving tokens; service.py handles FE app credentials; execution.py/recovery.py protect and recover execution.'],
        ['jobs.py; worker.py<br/>reconciliation.py','Durable job scheduling, fenced leases, retries and app-only execution. Reconciliation closes a finished case\'s stale graph pause and records memory without a model call.'],
        ['persistence.py; memory.py<br/>context.py; clients.py','Graph checkpoints, per-student notes, verified runtime identity, and confirmation/resume handling. CLI uses the same workflow in explicit demo mode.'],
        ['tests/; scripts/; seed/; docs/','Regression/security tests; seed, integrity, approval and demo utilities; identity/rules examples; design and acceptance records. .env.example documents settings; uv.lock pins dependencies.'],
    ],[171,340],9.2)
    p.heading('The model is one component, not the system')
    p.body('<b>LangChain</b> supplies model/tool abstractions. <b>Deep Agents</b> adds planning, skills, filesystem context and subagents. <b>LangGraph</b> executes and checkpoints the graph and human pauses. <b>Pydantic</b> validates structured inputs/verdicts. HARNESS_MODEL selects the configured provider, including Databricks or Azure OpenAI; there is no secretly substituted live model.')
    p.body('<b>Skills are not RAG:</b> the FE skill is a small hand-written Markdown rules document loaded on demand. No vector database/retrieval pipeline is implemented. Protected rules, skills and memory files cannot be rewritten by model file tools. Context compression summarises/offloads long histories; a 25-model-call run cap limits loops. The generic subagent is disabled so it cannot inherit write powers.')
    p.body('<b>Vocabulary:</b> API = a program\'s callable interface. A tool is an allowed function the model can request. HITL = human in the loop. A checkpoint saves execution position; a memory note saves useful case facts across conversations.')
    p.end()

    p=Page(c,3,'Identity: who may call what?','Authentication proves identity. Authorization determines allowed operations.')
    p.body('<b>Browser flow (BFF = backend for frontend):</b> React visits /auth/login; MSAL starts Microsoft authorization-code sign-in with PKCE/state/nonce handling. /auth/callback completes the exchange. The backend maps verified <b>(tid, oid)</b> to S1/S2/I1/I2, stores an encrypted account/token cache and issues a random HttpOnly session cookie. Model arguments and email prefixes never choose identity.')
    p.table(['Credential / protocol','Purpose and boundary'],[
        ['OIDC ID token','Identifies the person to the harness. It is not an MCP API access token. OAuth 2.0 governs API access; OIDC adds sign-in identity. MSAL implements the client protocol.'],
        ['Browser cookie + CSRF','Browser sends opaque session reference, not Entra tokens. Writes require CSRF token and exact Origin; CORS permits configured origins. Hosted cookies require Secure; HTTP is explicit loopback development only.'],
        ['Delegated access token','Separate token per API, scope mcp.access. FE token cannot be reused at Zambeel. A student/instructor acts with the mapped role allowed by the receiving MCP.'],
        ['Application access token','Client-credentials flow identifies a service without a signed-in student. Worker gets FE Cases.ExecuteApproved; FE gets Zambeel Academic.Read and Enrollment.ExecuteApproved. Each needs an allowed app identity too.'],
        ['JWT / RS256 / JWKS','JSON Web Token contains signed claims, not encrypted data. RS256 verifies an RSA/SHA-256 signature using Entra public keys (JWKS), then issuer/tenant/audience, lifetime, v2 version, caller azp, scopes/roles and mapping are checked.'],
        ['MCP / streamable HTTP','Standard tool/prompt/completion messages over HTTP(S), using the official Python SDK. ClientSession initializes then calls a tool with the intended Bearer token. MCP is not the LLM or the academic database.'],
    ],[150,361],9.3,padding=4.5)
    p.heading('Claims you should recognise')
    p.body('<b>iss</b> = issuer; <b>tid</b> = tenant; <b>oid</b> = stable user/service object ID; <b>aud</b> = receiving API; <b>exp / iat</b> = expiry/issued time; <b>azp</b> = calling application; <b>scp</b> = delegated scopes; <b>roles</b> = assigned user roles or application permissions. For the implemented v2 validators, audience is the API client ID; scope requests use its api:// identifier. No browser OBO flow is used.')
    p.callout('<b>Two independent checks:</b> FastAPI guards its sessions/history and identity conflicts. Each MCP validates its own token and business permissions. A valid harness session does not itself grant Instructor access on FE. Missing/invalid credentials fail closed; there is no demo fallback.')
    p.body('<b>Private state:</b> Fernet encrypts auth.db payloads; cookie references are hashed. The persistent auth key must survive restart. Tokens stay out of model messages, checkpoints and job payloads. Callback logging is suppressed by the launcher. Invalid token = 401; insufficient permission = 403; unavailable key service = 503.')
    p.body('<b>Browser protections:</b> PKCE binds the code exchange to a secret verifier; state/nonce bind login responses. CSRF blocks forged cross-site writes; CORS controls which browser origins may read API responses. MSAL is Microsoft\'s authentication client library.')
    p.end()

    p=Page(c,4,'One force-enrollment request','Example: S1 requests CS412 section S1; I1 owns that section.')
    p.table(['Step','Who acts / what is saved'],[
        ['1. Plan and check','Main agent writes a plan, reads the FE skill and calls the read-only eligibility-checker. Zambeel returns facts and blocking/advisory rule codes; the subagent returns a structured verdict.'],
        ['2. Prepare and confirm','submit_case triggers a student pause. Trusted confirmation handling prepares an eligible case (DRAFT -> AWAITING_CONFIRMATION); explicit yes saves SUBMITTED, no saves CANCELLED. Ineligible requests cannot create a valid case just because the model says yes.'],
        ['3. Route to owner','FE rechecks eligibility and routes the confirmed case to AWAITING_APPROVAL. The graph reaches its execute_enrollment instructor pause. Saved confirmation can be recovered if the agent/API stops before routing finishes.'],
        ['4. Instructor decides','I1 calls FE decide_case with an Instructor token. FE checks section ownership. Reject -> REJECTED. Approve -> signed approval + APPROVED + one execution job in the same database transaction.'],
        ['5. Execute with service authority','Worker calls execute_approved_case(case_id). FE derives student/section from the saved case, verifies/consumes approval and enters EXECUTING atomically, then rechecks academics. Zambeel authorizes FE and writes idempotently.'],
        ['6. Show outcome','Persist COMPLETED with saved enrollment, or a terminal failure/rejection. Returning student\'s authorized history read reconciles the graph and writes one case-derived memory note without another model/enrollment call.'],
    ],[123,388],9.4)
    p.heading('Canonical happy-path states')
    p.callout('DRAFT -> AWAITING_CONFIRMATION -> SUBMITTED -><br/>AWAITING_APPROVAL -> APPROVED -> EXECUTING -> COMPLETED')
    p.body('<b>Branches:</b> decline or submission-time loss of eligibility can cancel; instructor refusal rejects; invalid/expired approval or final academic refusal can fail. APPROVED does not mean enrolled. Only a saved COMPLETED result with enrollment evidence does. Every legal state transition records its actor/action and old/new state.')
    p.heading('FE-1 to FE-8: deterministic placeholder policy')
    p.body('1 Full section required (open alternative is advisory). 2 Completed prerequisites. 3 No timetable clash. 4 Credit cap 20. 5 No probation (CGPA below 2.0). 6 Section year/CGPA restrictions. 7 Instructor accepts FE and cap remains. 8 Not already enrolled; offered this term. <b>These are team test rules, not official LUMS policy.</b> Checks occur before confirmation, at submission and at execution; the final enrollment write checks capacity under database coordination.')
    p.end()

    p=Page(c,5,'Why offline work is not lost','The browser session, the business approval and the execution job are different things.')
    p.body('<b>Atomic outbox:</b> APPROVED and its unique execution_jobs row commit together. If enqueue fails, approval rolls back too. This closes the crash gap where approval was saved but nobody knew to execute it. The job contains case_id and scheduling/result metadata, not a user token or editable academic details. <b>HMAC</b> is a keyed message authentication code: FE signs/verifies approval with its private shared signing secret; the model cannot mint it.')
    p.table(['Failure / situation','Recovery mechanism'],[
        ['Student closes browser','SSE relay is separate from the detached in-process graph runner. Browser disconnect does not cancel the run. After approval, the independent service worker needs no student session at all.'],
        ['API/backend restarts','Cases, graph checkpoints and notes persist. FE periodically routes saved SUBMITTED cases and recovers missing approved/in-flight jobs. Restarted API can reconcile the final saved result. An arbitrary interrupted model turn is not automatically replayed.'],
        ['Worker dies after claiming','Claim uses a short SQLite transaction and a random lease token. Expired leases are reclaimable; stale workers cannot acknowledge a newer lease. Lease coordination alone does not authorize enrollment.'],
        ['Reply lost after enrollment','Retry/reconcile the SAME case ID. FE/Zambeel find the saved enrollment; a unique idempotency key prevents another row. Do not assume a timeout means the write did not happen.'],
        ['Two retries overlap','FE uses per-case OS file locks released on process death; Zambeel also uses SQLite write coordination and unique constraints. No academic HTTP call holds an FE write transaction open.'],
        ['Token expiry','Student Entra-token expiry does not block app-authorized execution. An unconsumed 24-hour approval expiry DOES stop for instructor review. Workers cannot renew it silently.'],
    ],[145,366],9.4,padding=6)
    p.heading('The worker-only service contract')
    p.callout('<b>execute_approved_case(case_id) -></b> case_id, state, outcome, retryable, enrollment_id, error_code, message.<br/><b>completed:</b> save success. <b>terminal:</b> stop automatic retries and retain reason. <b>retry:</b> back off with the same case ID.')
    p.body('<b>Operational failures are separate:</b> authentication/configuration/protocol failures block a job for repair; they are not academic rejection. Transient transport failures retry with capped exponential backoff. After repair, an operator explicitly retries blocked work. The worker endpoint is never in the model\'s tool allowlist and refuses delegated student/instructor credentials.')
    p.body('<b>Ownership:</b> Ammar wrote the queue/leases, worker client and graph/memory reconciliation. Nausherwan wired the FE transaction, restricted endpoint, FE-to-Zambeel service identity, case locking and periodic recovery. Their agreement is enforced across both sides, not by a prompt.')
    p.end()

    p=Page(c,6,'Data, UI and MCP surfaces','What persists, what is visible, and why the services are split.')
    p.table(['Storage','Meaning'],[
        ['harness.db','Synthetic students/instructors, courses, prerequisites, transcript, offerings/time slots, enrollments; plus cases, approvals, audit_events, notifications, API session metadata and execution_jobs. Shared local database is deliberate for this increment.'],
        ['checkpoints.db','SqliteSaver persists graph messages, tool calls and pending human interrupts per thread. Session ID = thread ID = associated case ID; a session may exist before a case is prepared.'],
        ['store.db','SqliteStore contains long-term notes under the authenticated student namespace. save_case_note derives facts from terminal cases; repeated reconciliation does not duplicate the case note.'],
        ['auth.db + protected key','Separate encrypted flows/sessions/account/token caches. Losing the encryption key invalidates access to sessions; it does not delete business cases. Secrets/keys and data are ignored by git.'],
    ],[135,376],9.3)
    p.heading('Nausherwan\'s server surfaces')
    p.body('<b>Zambeel MCP:</b> student profile/enrollments, catalogue/sections, eligibility and scan_my_fe_options. FE-only operations include get_student_record, academic_catalogue, eligibility_record, get_section, course_details, enrollment_result and enroll, with permission checks appropriate to the call. Enroll derives the student from saved case evidence and checks consumed owner approval.')
    p.body('<b>FE MCP:</b> prepare_case, confirm_case, submit_case, execute_enrollment, decide_case, get_my_cases, get_case_status and notify_student. The new execute_approved_case is worker-only. Exposing a server tool does not automatically put it in the model allowlist: confirmation and instructor actions are controlled application paths.')
    p.body('<b>Prompts/completions:</b> FE exposes force_enroll(school, course, section), with dependent school -> course -> section suggestions. This is MCP prompt functionality; a React /fe dropdown is not implemented. The browser chat still uses natural-language requests. CLI/stdio remains explicit local demo; authenticated MCP mode uses HTTP Bearer credentials.')
    p.heading('Streaming and the current dashboard')
    p.body('React receives FastAPI <b>Server-Sent Events (SSE)</b>: plan/tool/subagent/interrupt/outcome updates. These are graph-step updates, not token-by-token model streaming; HTTP SSE to the browser is distinct from MCP streamable HTTP. Cookies/CSRF and ownership checks apply before a stream starts. Browser reopens saved history after disconnect.')
    p.callout('<b>Known UI gap:</b> authenticated profile and student FE cases use MCPs. Instructor pending/decided lists and notifications lack agreed MCP read contracts and report unavailable; an instructor can open an owned case by ID. Sakai courses/due work and other automations are outside the current force-enrollment increment.',AMBER)
    p.end()

    p=Page(c,7,'What is proven; how to demonstrate','Keep implemented code, synthetic integration and live acceptance separate.')
    p.table(['Evidence as of 19 November','Interpretation'],[
        ['354 passed; 11 live tests deselected','Full offline regression passed in 181.04 s. Frontend typecheck/build passed. One existing SDK/Pydantic annotation warning remains.'],
        ['4 new full-stack scenarios','Approve with student offline/lease recovery/API restart; reject; ineligible S2 despite a false model verdict; student cancellation. BFF, graph/subagent, actual HTTP MCP validators, workflow, worker and persistent stores are real. Microsoft issuance/model replies are synthetic.'],
        ['Receiving-side security/recovery tests','Wrong signature/issuer/audience/scope/role; app allowlists; ownership; atomic rollback; concurrency; process-death lock release; expired approval; SUBMITTED recovery and lost-response execution.'],
        ['Actual cloud acceptance','Microsoft discovery and redirect worked earlier. Real callback/token exchange, live model plus authenticated worker flow and hosted recovery have NOT been verified for this increment. Historical October live-model runs were local demo evidence, not this authentication flow.'],
    ],[167,344],9.2)
    p.heading('Localhost demonstration ladder')
    p.body('<b>1. UI only:</b> frontend VITE_USE_MOCK=true; npm run dev -- --host localhost. This is scripted browser data. <b>2. Offline integration:</b> uv run --frozen pytest -q tests/test_force_enrollment_stack.py tests/test_mcp_entra.py. No Microsoft passwords/model key required. <b>3. Real integrated localhost:</b> provision private process files, then run the five processes below. Microsoft sign-in still needs internet.')
    p.table(['Process / port','Command after selecting its private HARNESS_ENV_FILE'],[
        ['Zambeel / 8102','uv run --frozen python -m harness.mcp zambeel'],
        ['FE / 8101','uv run --frozen python -m harness.mcp fe'],
        ['FastAPI / 8000','uv run --frozen python -m harness.api'],
        ['Worker / no UI port','uv run --frozen python -m harness.worker'],
        ['React / 5173','From frontend/: VITE_USE_MOCK=false; VITE_API_BASE_URL=http://localhost:8000; npm run dev -- --host localhost --port 5173 --strictPort'],
    ],[127,384],9.1,padding=5)
    p.body('<b>Live prerequisites:</b> separate FE/worker credentials, allowed app IDs, consented application roles, v2 API tokens and model settings. The harness secret is not a substitute. MCP servers use HARNESS_MCP_AUTH_MODE=entra; API uses HARNESS_AUTH_MODE=bff. HTTP requires explicit loopback allowance. Preserve the shared test DB and approval key. S1/S2/I1/I2 are mapped; actual token roles need verification.')
    p.body('<b>Demo:</b> S1 confirms CS412-S1; copy case ID and close S1 browser. I1 opens ID and approves; worker completes. Restart API/worker; S1 returns to one enrollment, audit and one note. Use separate browser profiles. Config: README.md and docs/entra-mcp.md.')
    p.end()

    p=Page(c,8,'Questions Sir is likely to ask','Short answers you can expand using the preceding pages.')
    qa=[
        ('Why use an agent if rules are deterministic?', 'The model interprets the request, plans, asks clarifying questions and explains results. Deterministic Python authorizes every state change and academic write. A wrong model verdict cannot override the gate.'),
        ('Why two MCP servers?', 'Zambeel is the system adapter; FE is the approval process. A future PeopleSoft integration changes the academic adapter without rebuilding the orchestrator, provided its contract is preserved. No real PeopleSoft API integration exists yet.'),
        ('Why does the instructor not resume the student agent?', 'An instructor token is not a student credential. FE records the decision; an app-authorized worker executes the saved case. Later the student reads a reconciled result without another LLM run.'),
        ('Is human-in-the-loop the security mechanism?', 'No. HITL requests consent/approval; role and ownership, HMAC signature/expiry/single-use, eligibility checks and idempotency enforce it. Write pauses allow approve/reject, not arbitrary argument edits.'),
        ('Entra token versus approval token?', 'Entra signs API identity/access claims with asymmetric keys. FE signs a case-bound HMAC approval with its private approval secret. They have different issuers, purposes and expiry rules.'),
        ('What prevents two enrollments?', 'At-least-once retries use the same case ID. Unique enrollment keys, database coordination and FE case locking make the write idempotent; leases fence worker acknowledgements. This is not a claim of exactly-once network delivery.'),
        ('Why no async SQLite rewrite / generic adapter?', 'Explicit MCP wrappers perform async HTTP calls behind the existing sync graph runner. This preserves tested checkpoints and tool names; the October async-refactor proposal was not implemented literally. Later instructions allow async changes only where justified.'),
        ('Can this scale to multiple machines?', 'Current guarantee targets a single VM, shared local SQLite/filesystem and one API process for run locks. Multiple hosts require redesigned coordination, persistent services and authorization contracts, not copied database files.'),
        ('What is actually left?', 'Real Entra/service credentials and grants, configured model, live/hosted acceptance and instructor-list/notification interfaces. Expired approval requires review; explicit reapproval is not implemented. Sakai and other automations are deferred.'),
    ]
    for q,a in qa:
        p.y-=pdraw(c,q,42,p.y,511,10.5,TEAL,True)+3
        p.y-=pdraw(c,a,42,p.y,511,9.6)+9
    p.body('<b>Source trail:</b> November work division pp. 6-7; October infrastructure plan WP7/WP9; user\'s later BFF, offline-recovery and FE-only agreements. Reviewed code: agent.py, api/, mcp/, workflow/approvals/cases, jobs/worker/reconciliation and persistence/memory. For detailed file references and test evidence: docs/ammar-agent-integration.md and docs/force-enrollment-acceptance.md. No credentials are included.')
    p.end();c.save()


def slide_header(c,num,title,subtitle):
    c.setFillColor(INK);c.rect(0,0,960,540,fill=1,stroke=0)
    c.setFillColor(TEAL);c.rect(0,530,960,10,fill=1,stroke=0)
    pdraw(c,'GROUP 4  /  FORCE ENROLLMENT  /  AMMAR + NAUSHERWAN',36,510,880,10,colors.HexColor('#71D5CD'),True)
    pdraw(c,title,36,478,888,29,WHITE,True)
    pdraw(c,subtitle,36,434,888,13,colors.HexColor('#D0DFEB'))
    pdraw(c,'19 NOV 2026 | ammar fa933cc | synthetic academics; live Entra/model acceptance pending',36,25,850,9,colors.HexColor('#D0DFEB'))
    pdraw(c,f'{num} / 3',895,25,45,9,WHITE)


def caption(c,text,top):
    pdraw(c,text,36,top,888,14,WHITE)


def presentation():
    c=canvas.Canvas(str(OUT/'SProj_Visual_Meeting_Map.pdf'),pagesize=(960,540))
    c.setTitle('LUMS Process Orchestrator | Visual Meeting Map')
    c.setAuthor('SProj Group 4 | Ammar - Agent and Orchestrator')
    slide_header(c,1,'The model plans. The services enforce.','A trusted path from student intent to an authorized academic write.')
    box(c,36,270,172,108,'1  Student browser','React chat + confirmation<br/>Opaque cookie + CSRF',title_size=16,body_size=12)
    box(c,246,270,224,108,'2  FastAPI + agent','BFF login; verified identity<br/>Plan -> read-only checker<br/>LangGraph human pauses',fill=PALE,title_size=16,body_size=12)
    box(c,508,270,180,108,'3  FE MCP','Own case + approval<br/>Validate every write<br/>Worker-only operation',fill=PALE,title_size=16,body_size=12)
    box(c,726,270,198,108,'4  Zambeel MCP','Academic facts + rules<br/>Authorized enrollment<br/>Synthetic DB today',title_size=16,body_size=12)
    for a,b in [(208,246),(470,508),(688,726)]: arrow(c,a,322,b,322,colors.HexColor('#71D5CD'))
    box(c,246,143,224,84,'Microsoft Entra','Different access token per API<br/>Both MCPs validate independently',title_size=15,body_size=11)
    arrow(c,358,227,358,270,colors.HexColor('#71D5CD'))
    box(c,508,143,180,84,'Durable worker','Application identity<br/>case_id only; no user token',fill=PALE,title_size=15,body_size=11)
    arrow(c,598,227,598,270,colors.HexColor('#71D5CD'))
    box(c,726,143,198,84,'Persistent records','Case / approval / audit / job<br/>Checkpoint + student memory',title_size=15,body_size=11)
    caption(c,'Ammar: login, client, worker, recovery.    Nausherwan: server auth, service gates, atomic handoff.',104)
    caption(c,'Say: "The LLM proposes actions; Python and database checks decide whether they are allowed."',74)
    c.showPage()

    slide_header(c,2,'A request has two human decisions','S1 asks for CS412-S1. The owning instructor is I1. Approved is not yet enrolled.')
    specs=[(36,'1  Check','Agent delegates.<br/>FE verifies academics.'),(266,'2  Confirm','Student explicitly agrees.<br/>Save SUBMITTED.'),(496,'3  Decide','I1 ownership + role check.<br/>Approve or reject.'),(726,'4  Execute','App-only worker -> FE.<br/>Recheck -> enroll once.')]
    for x,t,b in specs: box(c,x,272,198,112,t,b,PALE if x in (266,496) else BLUE,17,12)
    for a,b in [(234,266),(464,496),(694,726)]: arrow(c,a,328,b,328,colors.HexColor('#71D5CD'))
    for x,t,b in [(36,'Ineligible','Explain blocking rules.<br/>No valid enrollment request.'),(266,'Student declines','CANCELLED.<br/>No approval or enrollment.'),(496,'Instructor rejects','REJECTED.<br/>No enrollment write.'),(726,'Complete','COMPLETED + audit.<br/>Returning student gets note.')]:
        box(c,x,136,198,91,t,b,AMBER if x!=726 else PALE,15,11)
        arrow(c,x+99,272,x+99,227,colors.HexColor('#71D5CD'))
    caption(c,'Approval path: APPROVED + unique execution job commit together, or both roll back.',105)
    caption(c,'Safety: valid signed approval + owner + eligibility + case-ID idempotency + full transition audit.',74)
    c.showPage()

    slide_header(c,3,'Close the browser. Keep the case.','Durable recovery works from saved authority, not from a student remaining online.')
    steps=[(36,'SAVE','Confirmation and approval<br/>are persistent records.'),(266,'CLAIM','Worker leases the job.<br/>Expired lease is recoverable.'),(496,'RECONCILE','Retry same case ID.<br/>Reuse existing enrollment.'),(726,'RETURN','Reload saved outcome.<br/>One note; no new LLM call.')]
    for x,t,b in steps: box(c,x,282,198,101,t,b,PALE,17,12)
    for a,b in [(234,266),(464,496),(694,726)]: arrow(c,a,330,b,330,colors.HexColor('#71D5CD'))
    box(c,36,124,425,119,'VERIFIED LOCALLY','354 tests passed; frontend checks/build passed.<br/>Full-stack HTTP services, validators, workflow and worker.<br/>Microsoft token issuance + model replies are simulated.',title_size=17,body_size=12)
    box(c,491,124,433,119,'LIVE ACCEPTANCE STILL PENDING','Provision separate FE/worker credentials and grants + model.<br/>Real login -> I1 approval -> offline/restart -> one enrollment.<br/>Instructor lists/notifications remain an interface gap.',fill=AMBER,title_size=17,body_size=12)
    caption(c,'Student token expiry does not cancel service execution. Expired 24-hour approval still requires review.',93)
    caption(c,'Say: "Our integration is implemented and locally tested; real Entra/model acceptance is the next gate."',63)
    c.showPage();c.save()


if __name__=='__main__':
    guide();presentation()
    for f in OUT.glob('SProj_*.pdf'): print(f)
