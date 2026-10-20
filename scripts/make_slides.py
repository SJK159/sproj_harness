"""Builds docs/LUMS-Orchestrator-Slides.pdf: 4 landscape slides for the instructor.

    uv run --with reportlab python scripts/make_slides.py [output.pdf]

1. Infrastructure and outside services   2. One request, end to end
3. Tool calling                          4. Key decisions and status
Facts come from the repo (CLAUDE.md, docs/decisions.md, scripts/list_agent_tools.py); update them here when they change.
"""

import sys

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/LUMS-Orchestrator-Slides.pdf"
W, H = 960, 540  # 16:9 in points
X0, X1 = 36, 924

NAVY = colors.HexColor("#1F3A5F")
TEAL = colors.HexColor("#2A7F8E")
TEAL_SOFT = colors.HexColor("#E3F1F3")
SAND = colors.HexColor("#F4EFE6")
GREY = colors.HexColor("#5B6470")
GREY_SOFT = colors.HexColor("#EEF0F3")
LINE = colors.HexColor("#8A939E")
RED_SOFT = colors.HexColor("#F7E4E1")
GREEN = colors.HexColor("#3D7D4F")
GREEN_SOFT = colors.HexColor("#E2F0E5")
AMBER = colors.HexColor("#B7791F")
AMBER_SOFT = colors.HexColor("#FBF0DA")
NAVY_SOFT = colors.HexColor("#E4EAF2")
INK = colors.HexColor("#1D232B")
WHITE = colors.white

FOOTER = ("Group 4 “Height Boosters” · SProj 2026-27 · Supervisor: Dr. Ali Khawaja · "
          "synthetic data only; FE rules are placeholders, not LUMS policy")


def style(size=9, bold=False, color=INK, leading=None, align=0):
    return ParagraphStyle("s", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.28, textColor=color, alignment=align)


def para(c, html, x, top, w, st):
    """Draw a wrapped paragraph with its top at `top`; return its height."""
    p = Paragraph(html, st)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, top - h)
    return h


def rbox(c, x, y, w, h, fill=WHITE, stroke=LINE, r=6, sw=0.9):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(sw)
    c.roundRect(x, y, w, h, r, stroke=1, fill=1)


def card(c, x, top, w, h, title, body, fill=WHITE, stroke=LINE, tsize=9.5, bsize=8, tcolor=NAVY, pad=7):
    rbox(c, x, top - h, w, h, fill, stroke)
    used = para(c, title, x + pad, top - pad, w - 2 * pad, style(tsize, True, tcolor))
    if body:
        para(c, body, x + pad, top - pad - used - 2, w - 2 * pad, style(bsize, color=INK))


def arrow(c, x1, y1, x2, y2, color=LINE, width=1.1, head=5.5):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 0.01)
    ux, uy = dx / length, dy / length
    path = c.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(x2 - head * ux - head * 0.55 * uy, y2 - head * uy + head * 0.55 * ux)
    path.lineTo(x2 - head * ux + head * 0.55 * uy, y2 - head * uy - head * 0.55 * ux)
    path.close()
    c.drawPath(path, stroke=0, fill=1)


def elbow(c, x1, y1, x2, y2, color=LINE):
    """Right-angle connector: across to the midpoint, then vertically, then across with an arrowhead."""
    mx = (x1 + x2) / 2
    c.setStrokeColor(color)
    c.setLineWidth(1.1)
    c.line(x1, y1, mx, y1)
    c.line(mx, y1, mx, y2)
    arrow(c, mx, y2, x2, y2, color)


def header(c, n, title, subtitle):
    c.setFillColor(NAVY)
    c.rect(0, H - 72, W, 72, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.rect(0, H - 75, W, 3, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(X0, H - 38, title)
    c.setFillColor(colors.HexColor("#CFE3E8"))
    c.setFont("Helvetica", 11)
    c.drawString(X0, H - 58, subtitle)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(X1, H - 38, f"{n} / 4")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 7.5)
    c.drawString(X0, 16, FOOTER)
    c.drawRightString(X1, 16, "LUMS Process Orchestrator · force enrollment")


# ------------------------------------------------------------------------------------------------- slide 1

def slide_infrastructure(c):
    header(c, 1, "LUMS Process Orchestrator: infrastructure",
           "A deep agent in front of a mock Zambeel. A student asks in plain English; Python enforces every rule.")
    gx, gw = X0, 600  # diagram area

    # clients
    top = 448
    clients = [
        ("Web UI", "React 18 + Vite + Tailwind (<font face='Courier'>frontend/</font>): chat, live thinking panel, "
                   "case lane, instructor review screen"),
        ("Student CLI", "<font face='Courier'>harness.cli</font>: the same agent in a terminal, with a confirm prompt"),
        ("Instructor", "Approve or reject in the web view or with <font face='Courier'>scripts/approve.py</font>"),
    ]
    cw = (gw - 2 * 12) / 3
    for i, (t, b) in enumerate(clients):
        card(c, gx + i * (cw + 12), top, cw, 58, t, b, fill=SAND, stroke=LINE)
    for i in range(3):
        arrow(c, gx + i * (cw + 12) + cw / 2, top - 58, gx + i * (cw + 12) + cw / 2, top - 72)

    # API
    top = 376
    card(c, gx, top, gw, 34, "HTTP API: FastAPI 0.143 + Server-Sent Events (<font face='Courier'>harness.api</font>)",
         "Streams each agent step (plan, tool calls, sub-agent steps, case updates, pauses) to the browser. "
         "Local only (127.0.0.1).", fill=WHITE, tsize=9, bsize=7.6)
    arrow(c, gx + gw / 2, top - 34, gx + gw / 2, top - 46)

    # deep agent
    top = 330
    rbox(c, gx, top - 100, gw, 100, TEAL_SOFT, TEAL)
    para(c, "Deep agent: <b>deepagents 0.7.28</b> on <b>LangGraph 1.2.15</b> (langchain 1.4.6)",
         gx + 8, top - 7, gw - 16, style(9.5, True, NAVY))
    iw = (gw - 16 - 10) / 2
    card(c, gx + 8, top - 26, iw, 66, "Main agent",
         "Plans with <font face='Courier'>write_todos</font>, reads the rules skill, delegates checks with "
         "<font face='Courier'>task</font>, calls the write tools (each one behind a pause).",
         fill=WHITE, stroke=TEAL, tsize=9, bsize=7.8)
    card(c, gx + 8 + iw + 10, top - 26, iw, 66, "Eligibility-checker sub-agent",
         "Read-only tools; returns a structured <font face='Courier'>EligibilityVerdict</font> (codes + rule labels). "
         "Can ask the student one clarifying question.",
         fill=WHITE, stroke=TEAL, tsize=9, bsize=7.8)
    arrow(c, gx + gw / 2, top - 100, gx + gw / 2, top - 114)

    # storage + gates
    top = 214
    stores = [
        ("Workflow + gates", "Python: case state machine, HMAC approval tokens, eligibility re-checks"),
        ("harness.db", "SQLite: mock Zambeel, cases, approvals, append-only audit log, notices"),
        ("checkpoints.db", "SQLite checkpointer: paused runs survive restarts; thread = case id"),
        ("store.db", "SqliteStore: per-student memory notes (long-term memory)"),
        ("skills/ + seed/", "SKILL.md rules (FE-1..FE-8) and agent rules; read-only to the agent"),
    ]
    sw_ = (gw - 4 * 9) / 5
    for i, (t, b) in enumerate(stores):
        fill = NAVY_SOFT if i == 0 else GREY_SOFT
        card(c, gx + i * (sw_ + 9), top, sw_, 82, t, b, fill=fill, tsize=8.6, bsize=7.4, pad=6)

    para(c, "<b>Stack:</b> Python 3.12, uv, pytest · 218 offline tests + 11 live tests on the real model · "
            "no real Zambeel / PeopleSoft and no real student data: everything is a synthetic SQLite mock.",
         gx, 116, gw, style(8.4, color=GREY))

    # outside services
    sx, swd = 660, X1 - 660
    para(c, "Outside services", sx, 448, swd, style(12, True, NAVY))
    services = [
        ("Databricks Free Edition: Model Serving",
         "The LLM: <b>gpt-oss-120b</b>, called through its OpenAI-compatible Chat Completions API with "
         "langchain-openai <font face='Courier'>ChatOpenAI</font>, by the deep agent over HTTPS. "
         "Model name set by env var, never hardcoded.",
         AMBER_SOFT, AMBER),
        ("LangSmith", "Tracing: every plan, tool call, sub-agent run and pause, for debugging and demos.",
         WHITE, LINE),
        ("GitHub", "Private repository <font face='Courier'>SJK159/sproj_harness</font>.", WHITE, LINE),
        ("Claude Design", "Generated the React frontend from our written design prompt "
                          "(<font face='Courier'>docs/frontend-design-prompt.md</font>).", WHITE, LINE),
        ("Google Fonts", "Web fonts loaded by the UI (its only external call).", WHITE, LINE),
    ]
    top = 426
    for t, b, fill, stroke in services:
        h = 72 if fill is AMBER_SOFT else 50
        card(c, sx, top, swd, h, t, b, fill=fill, stroke=stroke, tsize=9, bsize=7.8)
        top -= h + 8
    # agent -> model: around the gap between the diagram and the services column
    c.setStrokeColor(AMBER)
    c.setLineWidth(1.3)
    c.line(gx + gw, 300, sx - 12, 300)
    c.line(sx - 12, 300, sx - 12, 390)
    arrow(c, sx - 12, 390, sx - 1, 390, AMBER, 1.3)


# ------------------------------------------------------------------------------------------------- slide 2

def slide_flow(c):
    header(c, 2, "One request, end to end",
           "“Can I get force enrolled in CS412 section S1?”: two pauses for people, three eligibility "
           "checks, one enrollment.")
    lanes = ["Student", "Main agent", "Eligibility checker", "Python gates + DB", "Instructor"]
    lane_h, top0, lx, lw = 64, 452, X0, 92
    cx0 = lx + lw + 6
    for i, name in enumerate(lanes):
        y = top0 - (i + 1) * lane_h
        c.setFillColor(GREY_SOFT if i % 2 == 0 else WHITE)
        c.rect(lx, y, X1 - lx, lane_h, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 8.6)
        c.drawString(lx + 6, y + lane_h / 2 - 3, name)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(cx0 - 3, top0, cx0 - 3, top0 - 5 * lane_h)

    # (lane, title, body, kind)
    steps = [
        (0, "1  Asks", "“force enroll me in CS412 S1”", "person"),
        (1, "2  Plans", "write_todos; reads SKILL.md rules", "agent"),
        (2, "3  Checks", "via task: all FE rules; returns the verdict", "agent"),
        (1, "4  Submits", "submit_case: PAUSE 1, ask the student", "pause"),
        (3, "5  Opens case", "re-check 1; DRAFT, AWAITING_ CONFIRMATION", "gate"),
        (0, "6  Confirms", "(declines: CANCELLED)", "person"),
        (3, "7  Routes", "re-check 2; AWAITING_ APPROVAL; notifies I1", "gate"),
        (1, "8  Waits", "execute_ enrollment: PAUSE 2; the process may stop here", "pause"),
        (4, "9  Approves", "owner check; signed token minted", "person"),
        (3, "10  Executes", "token verified; re-check 3; enrolls once", "gate"),
        (1, "11  Wraps up", "notify_student; save_case_note", "agent"),
    ]
    fills = {"person": (GREEN_SOFT, GREEN), "agent": (WHITE, TEAL), "pause": (AMBER_SOFT, AMBER),
             "gate": (NAVY_SOFT, NAVY)}
    n = len(steps)
    col = (X1 - cx0) / n
    bw, bh = col - 8, lane_h - 10
    centers = []
    for i, (lane, t, b, kind) in enumerate(steps):
        x = cx0 + i * col + 4
        y = top0 - (lane + 1) * lane_h + 5
        fill, stroke = fills[kind]
        rbox(c, x, y, bw, bh, fill, stroke, r=5)
        used = para(c, t, x + 4, y + bh - 4, bw - 8, style(7.6, True, NAVY, leading=8.8))
        para(c, b, x + 4, y + bh - 5 - used, bw - 8, style(6.6, color=INK, leading=7.8))
        centers.append((x, y, bw, bh))
    for (x1, y1, w1, h1), (x2, y2, w2, h2) in zip(centers, centers[1:], strict=False):
        elbow(c, x1 + w1, y1 + h1 / 2, x2, y2 + h2 / 2)

    # legend
    lx2, ly = cx0, top0 - 5 * lane_h - 20
    for label, kind in [("person decides", "person"), ("agent step (LLM chooses the tool)", "agent"),
                        ("pause (interrupt_on: approve / reject)", "pause"), ("deterministic Python", "gate")]:
        fill, stroke = fills[kind]
        rbox(c, lx2, ly, 12, 9, fill, stroke, r=2)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.6)
        c.drawString(lx2 + 16, ly + 1.5, label)
        lx2 += stringWidth(label, "Helvetica", 7.6) + 34

    # case states
    states = ["DRAFT", "AWAITING_CONFIRMATION", "SUBMITTED", "AWAITING_APPROVAL", "APPROVED", "EXECUTING",
              "COMPLETED"]
    y = 80
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8.6)
    c.drawString(X0, y + 6, "Case states")
    x = X0 + 70
    for i, s in enumerate(states):
        w = stringWidth(s, "Helvetica-Bold", 7.4) + 14
        last = i == len(states) - 1
        rbox(c, x, y, w, 18, GREEN_SOFT if last else WHITE, GREEN if last else TEAL, r=9)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawCentredString(x + w / 2, y + 6, s)
        if not last:
            arrow(c, x + w + 2, y + 9, x + w + 14, y + 9)
        x += w + 16
    para(c, "<b>Other endings:</b> ineligible: no case is ever created · student declines: CANCELLED · "
            "instructor rejects: REJECTED (never executes) · token refused or FE cap filled after approval: "
            "FAILED. <b>Every state change writes an append-only audit row</b> (who, what, from, to, when).",
         X0, 66, X1 - X0, style(8, color=INK))


# ------------------------------------------------------------------------------------------------- slide 3

def tool_table(rows, widths, header_fill):
    cell = style(7.9, leading=9.6)
    head = style(8.2, True, WHITE)
    data = [[Paragraph(h, head) for h in rows[0]]]
    data += [[Paragraph(f"<font face='Courier-Bold'>{r[0]}</font>", cell)] + [Paragraph(v, cell) for v in r[1:]]
             for r in rows[1:]]
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_fill),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_SOFT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9CFD6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def slide_tools(c):
    header(c, 3, "Tool calling",
           "The model chooses the next tool call; Python decides what that call is allowed to do.")
    w_main = [118, 264, 104]
    main = [
        ["Main agent tool", "What it does", "Kind"],
        ["write_todos", "Writes the plan for this request (shown as todos in the UI)", "planning"],
        ["read_file", "Reads the force-enrollment skill and rules (stands in for RAG)", "read"],
        ["task", "Delegates the eligibility check to the checker sub-agent", "delegation"],
        ["get_my_profile", "The student's own year, CGPA, credits, courses", "read"],
        ["get_my_cases", "The student's own cases and their states", "read"],
        ["list_offerings", "This term's catalogue: seats, full, FE accepted, slots", "read"],
        ["submit_case", "Opens the case after a fresh eligibility re-check", "write · PAUSE: student confirms"],
        ["execute_enrollment", "Verifies the signed approval token, re-checks, enrolls once",
         "write · PAUSE: instructor decides"],
        ["notify_student", "Sends the outcome notice", "write"],
        ["save_case_note", "Adds a memory note built from the case record", "write (memory)"],
    ]
    t = tool_table(main, w_main, NAVY)
    _, h = t.wrap(0, 0)
    t.drawOn(c, X0, 450 - h)
    main_bottom = 450 - h

    w_chk = [124, 284]
    chk = [
        ["Eligibility-checker tool", "What it does"],
        ["check_my_eligibility", "All FE rules for one section; every failing code with its rule label"],
        ["list_sections", "Sections of one course: time, seats, FE terms"],
        ["scan_my_fe_options", "The same check on every section this term, grouped"],
        ["list_offerings", "The term's catalogue"],
        ["get_my_profile", "The student's own record"],
        ["read_file", "The rules skill"],
        ["ask_student", "One clarifying question (PAUSE: the student's answer is the result)"],
        ["EligibilityVerdict", "Structured output: per section can_submit, codes, labels, suggestions"],
    ]
    t2 = tool_table(chk, w_chk, TEAL)
    _, h2 = t2.wrap(0, 0)
    t2.drawOn(c, X1 - sum(w_chk), 450 - h2)

    # how one call is handled
    top = min(main_bottom, 450 - h2) - 18
    para(c, "How one tool call is handled", X0, top, 400, style(10.5, True, NAVY))
    steps = [
        ("Model proposes", "tool name + arguments (gpt-oss-120b)", WHITE, TEAL),
        ("Pause if gated", "interrupt_on: approve / reject only; never edit or fake a result", AMBER_SOFT, AMBER),
        ("Python runs it", "student from the runtime context, never from the model's arguments", NAVY_SOFT, NAVY),
        ("Result back", "JSON (or {\"error\": …}) returned to the model", WHITE, TEAL),
    ]
    bw, gap, y_top = 196, 34, top - 20
    for i, (t_, b, fill, stroke) in enumerate(steps):
        x = X0 + i * (bw + gap)
        card(c, x, y_top, bw, 46, t_, b, fill=fill, stroke=stroke, tsize=9, bsize=7.8)
        if i < len(steps) - 1:
            arrow(c, x + bw + 4, y_top - 23, x + bw + gap - 4, y_top - 23)
    para(c, "<b>Guard rails:</b> write tools exist only on the main agent (checked by a test and "
            "<font face='Courier'>scripts/list_agent_tools.py</font>) · deepagents' general-purpose sub-agent is "
            "disabled · its built-in file tools (ls, glob, grep, write_file, edit_file, …) cannot write "
            "<font face='Courier'>/skills</font>, <font face='Courier'>/rules</font> or "
            "<font face='Courier'>/memories</font> · at most 25 model calls per run (main), 10 (checker).",
         X0, y_top - 58, X1 - X0, style(8.3, color=INK))


# ------------------------------------------------------------------------------------------------- slide 4

def slide_decisions(c):
    header(c, 4, "Key decisions",
           "Each one is logged with its reason and the alternatives in docs/decisions.md.")
    decisions = [
        ("deepagents on LangGraph",
         "Planning, sub-agents, human pauses, memory and skills come built in. One main agent plus one "
         "eligibility-checker sub-agent; the automatic general-purpose sub-agent is turned off."),
        ("Security in Python, not in prompts",
         "No enrollment without a valid approval token: HMAC-signed, 24-hour expiry, single use, bound to the "
         "case. Only the instructor side can mint one; no agent tool can."),
        ("Eligibility re-checked three times",
         "When the case opens, when it is submitted and at execution. The sub-agent's verdict is never trusted "
         "for a write, so a seat that fills after approval ends FAILED, not over capacity."),
        ("People approve through pauses",
         "interrupt_on with approve / reject only (no edit, no faked results). Conditional pauses (when) stop a "
         "repeated call from waiting for an instructor who never comes."),
        ("Durable, auditable state",
         "SQLite checkpointer with thread = case id, so a paused case survives a restart. Append-only audit log; "
         "enrollment is idempotent (case id is the key)."),
        ("Memory written only from records",
         "Per-student namespace. save_case_note builds each note from database rows, and the file tools cannot "
         "write memory, so nothing said in chat reaches a later prompt."),
        ("A rules file instead of RAG",
         "A hand-written SKILL.md with placeholder rules FE-1 to FE-8; every reason in an answer cites its rule "
         "label. RAG is out of scope for now."),
        ("Model: gpt-oss-120b on Databricks",
         "Free Edition, via ChatOpenAI. Fixes from live runs: declared the 128K window so summarization can "
         "trigger; capped calls per run; streamed step by step because Databricks rejects token-streamed replies."),
    ]
    cw, ch, gap = (X1 - X0 - 14) / 2, 66, 9
    for i, (t, b) in enumerate(decisions):
        col, row = i % 2, i // 2
        x = X0 + col * (cw + 14)
        top = 452 - row * (ch + gap)
        card(c, x, top, cw, ch, f"{i + 1}. {t}", b, fill=WHITE, stroke=TEAL, tsize=9.6, bsize=8)

    top = 452 - 4 * (ch + gap) - 4
    rbox(c, X0, top - 72, X1 - X0, 72, SAND, LINE)
    para(c, "Where we are", X0 + 10, top - 8, 300, style(10, True, NAVY))
    para(c, "Milestones M0 to M9 done: force enrollment end to end in the CLI and the web UI. 218 offline tests "
            "pass, plus 11 live tests on the real model; the integrity check finds every enrollment backed by an "
            "approval and every case with a complete audit trail.",
         X0 + 10, top - 24, (X1 - X0) / 2 - 20, style(8.2))
    para(c, "Open questions for you", X0 + (X1 - X0) / 2, top - 8, 300, style(10, True, NAVY))
    para(c, "1. Keep the deepagents package for the final system, or move to plain LangGraph?<br/>"
            "2. Which workflow next (e.g. dropping a course), and does it need instructor approval?",
         X0 + (X1 - X0) / 2, top - 24, (X1 - X0) / 2 - 10, style(8.2))


def main() -> None:
    c = canvas.Canvas(OUT, pagesize=(W, H))
    c.setTitle("LUMS Process Orchestrator: slides")
    c.setAuthor("Group 4, SProj 2026-27")
    for slide in (slide_infrastructure, slide_flow, slide_tools, slide_decisions):
        slide(c)
        c.showPage()
    c.save()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
