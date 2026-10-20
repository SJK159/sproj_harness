"""Builds docs/LUMS-Orchestrator-Slides.pdf: 4 presentation slides for the instructor (16:9).

    uv run --with reportlab python scripts/make_slides.py [output.pdf]

1. What we built (and the outside services)   2. One request, start to finish
3. How the assistant uses tools                4. Key decisions and where we are
Plain language on purpose; the technical detail is in docs/decisions.md and docs/LUMS-Orchestrator-Explained.pdf.
Facts come from the repo (tool lists: scripts/list_agent_tools.py; tests: uv run pytest); update them when they change.
"""

import sys

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/LUMS-Orchestrator-Slides.pdf"
W, H = 960, 540  # 16:9 in points
X0, X1 = 56, 904

NAVY = colors.HexColor("#1F3A5F")
TEAL = colors.HexColor("#2A7F8E")
TEAL_SOFT = colors.HexColor("#E3F1F3")
SAND = colors.HexColor("#F7F3EC")
GREY = colors.HexColor("#5B6470")
GREY_SOFT = colors.HexColor("#F1F3F6")
LINE = colors.HexColor("#C9CFD6")
GREEN = colors.HexColor("#3D7D4F")
GREEN_SOFT = colors.HexColor("#E2F0E5")
AMBER = colors.HexColor("#B7791F")
AMBER_SOFT = colors.HexColor("#FBF0DA")
NAVY_SOFT = colors.HexColor("#E4EAF2")
INK = colors.HexColor("#1D232B")
WHITE = colors.white

FOOTER = "LUMS Process Orchestrator  ·  Group 4 “Height Boosters”  ·  SProj 2026-27"


def style(size=12, bold=False, color=INK, leading=None, align=0):
    return ParagraphStyle("s", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.3, textColor=color, alignment=align)


def para(c, html, x, top, w, st):
    """Draw a wrapped paragraph with its top at `top`; return its height."""
    p = Paragraph(html, st)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, top - h)
    return h


def rbox(c, x, y, w, h, fill=WHITE, stroke=LINE, r=10, sw=1):
    c.setFillColor(fill)
    if stroke is not None:  # None: filled, no border
        c.setStrokeColor(stroke)
        c.setLineWidth(sw)
    c.roundRect(x, y, w, h, r, stroke=0 if stroke is None else 1, fill=1)


def disc(c, cx, cy, r, fill, label, size=16, color=WHITE):
    c.setFillColor(fill)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillColor(color)
    c.setFont("Helvetica-Bold", size)
    c.drawCentredString(cx, cy - size * 0.35, label)


def arrow(c, x1, y1, x2, y2, color=LINE, width=2, head=8):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 0.01)
    ux, uy = dx / length, dy / length
    c.line(x1, y1, x2 - ux * head * 0.8, y2 - uy * head * 0.8)
    path = c.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(x2 - head * ux - head * 0.55 * uy, y2 - head * uy + head * 0.55 * ux)
    path.lineTo(x2 - head * ux + head * 0.55 * uy, y2 - head * uy - head * 0.55 * ux)
    path.close()
    c.drawPath(path, stroke=0, fill=1)


def header(c, n, kicker, title, subtitle):
    c.setFillColor(TEAL)
    c.rect(0, H - 8, W, 8, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(X0, H - 46, kicker.upper())
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(X0, H - 80, title)
    para(c, subtitle, X0, H - 92, X1 - X0, style(13, color=GREY))
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(X0, 34, X1, 34)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 9)
    c.drawString(X0, 20, FOOTER)
    c.drawRightString(X1, 20, f"{n} / 4")


# ------------------------------------------------------------------------------------------------- slide 1

def slide_what(c):
    header(c, 1, "What we built", "An AI assistant for force enrollment",
           "Students ask in plain English. The assistant checks the rules, asks the right people to approve, "
           "and completes the request.")
    top, h = 400, 210

    # people
    x, w = X0, 220
    rbox(c, x, top - h, w, h, SAND, None)
    para(c, "People", x + 18, top - 16, w - 36, style(15, True, NAVY))
    for i, (who, what) in enumerate([("S", "<b>Student</b><br/>asks for a seat in a full course"),
                                     ("I", "<b>Instructor</b><br/>approves or rejects the request")]):
        cy = top - 78 - i * 72
        disc(c, x + 40, cy, 20, GREEN, who, 15)
        para(c, what, x + 70, cy + 17, w - 84, style(11.5, leading=15))
    para(c, "through a web app or the terminal", x + 18, top - h + 22, w - 36, style(10, color=GREY))

    # assistant
    x2, w2 = X0 + 268, 330
    arrow(c, X0 + w + 6, top - h / 2, x2 - 8, top - h / 2, TEAL)
    rbox(c, x2, top - h, w2, h, TEAL_SOFT, None)
    para(c, "The assistant", x2 + 20, top - 16, w2 - 40, style(15, True, NAVY))
    items = ["Understands the request", "Plans the steps it will take",
             "Checks every rule, using a helper agent", "Asks the student, then the instructor, to approve",
             "Enrolls the student and remembers the outcome"]
    for i, t in enumerate(items):
        cy = top - 62 - i * 28
        c.setFillColor(TEAL)
        c.circle(x2 + 28, cy + 4, 4, stroke=0, fill=1)
        para(c, t, x2 + 42, cy + 12, w2 - 60, style(12))

    # records
    x3, w3 = x2 + w2 + 48, X1 - (x2 + w2 + 48)
    arrow(c, x2 + w2 + 6, top - h / 2, x3 - 8, top - h / 2, TEAL)
    rbox(c, x3, top - h, w3, h, NAVY_SOFT, None)
    para(c, "University records", x3 + 18, top - 16, w3 - 36, style(15, True, NAVY))
    para(c, "A practice copy of Zambeel: students, courses, sections and enrollments.<br/><br/>"
            "A full history of every request and every change.",
         x3 + 18, top - 50, w3 - 36, style(11.5, leading=15))
    para(c, "synthetic data only", x3 + 18, top - h + 22, w3 - 36, style(10, color=GREY))

    # outside services
    para(c, "Outside services we use", X0, 150, 400, style(13, True, NAVY))
    chips = [("Databricks", "the AI model (gpt-oss-120b)"), ("LangSmith", "watching what the AI does"),
             ("GitHub", "our code"), ("Claude Design", "designed the web app")]
    cw, gap = (X1 - X0 - 3 * 14) / 4, 14
    for i, (name, role) in enumerate(chips):
        x = X0 + i * (cw + gap)
        rbox(c, x, 66, cw, 56, WHITE, LINE)
        para(c, name, x + 14, 112, cw - 28, style(13, True, TEAL))
        para(c, role, x + 14, 92, cw - 28, style(10.5, color=GREY))


# ------------------------------------------------------------------------------------------------- slide 2

def slide_flow(c):
    header(c, 2, "How it works", "One request, start to finish",
           "Example: a student asks <i>“Can I get force enrolled in CS412?”</i>")
    steps = [
        ("1", "Ask", "The student types the request in the chat.", TEAL),
        ("2", "Check", "The assistant checks every rule: prerequisites, clashes, credits, seats.", TEAL),
        ("3", "Confirm", "The student confirms before anything is sent.", GREEN),
        ("4", "Approve", "The instructor approves or rejects it.", GREEN),
        ("5", "Enroll", "The system verifies the approval and enrolls the student, exactly once.", NAVY),
        ("6", "Wrap up", "The student is notified, and the outcome is remembered.", TEAL),
    ]
    n = len(steps)
    col = (X1 - X0) / n
    cy = 330
    # "people decide" band behind steps 3 and 4
    rbox(c, X0 + 2 * col + 6, cy - 128, 2 * col - 12, 196, GREEN_SOFT, None, r=14)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(X0 + 3 * col, cy + 50, "PEOPLE DECIDE")
    for i, (num, title, text, color) in enumerate(steps):
        cx = X0 + col * i + col / 2
        disc(c, cx, cy, 26, color, num, 20)
        if i < n - 1:
            arrow(c, cx + 32, cy, cx + col - 32, cy, LINE)
        para(c, title, cx - col / 2 + 8, cy - 38, col - 16, style(15, True, NAVY, align=1))
        para(c, text, cx - col / 2 + 10, cy - 60, col - 20, style(11, color=INK, leading=14.5, align=1))

    # what can go wrong
    top = 168
    rbox(c, X0, 52, X1 - X0, top - 52, GREY_SOFT, None)
    para(c, "If something goes wrong, nothing unsafe happens", X0 + 20, top - 14, 600, style(13, True, NAVY))
    cases = [("Not eligible", "The assistant explains why. No request is created."),
             ("Declined or rejected", "The request is closed. Nothing changes."),
             ("Seat filled in the meantime", "The system stops safely. No over-enrollment.")]
    cw = (X1 - X0 - 40) / 3
    for i, (t, b) in enumerate(cases):
        x = X0 + 20 + i * cw
        para(c, t, x, top - 44, cw - 20, style(12, True, INK))
        para(c, b, x, top - 62, cw - 20, style(11, color=GREY, leading=14))


# ------------------------------------------------------------------------------------------------- slide 3

def slide_tools(c):
    header(c, 3, "Tool calling", "How the assistant uses tools",
           "The AI decides what to do next. Each tool does one job, and the risky ones need a person’s "
           "approval first.")
    # the loop
    lx, ly, s = X0, 108, 300  # square of four steps
    nodes = [
        ("Decide", "The AI picks the next tool", TEAL_SOFT, TEAL, lx, ly + s - 80),
        ("Approve?", "Only for actions: a person says yes or no", AMBER_SOFT, AMBER, lx + s - 130, ly + s - 80),
        ("Run", "The tool does its one job, in code", NAVY_SOFT, NAVY, lx + s - 130, ly),
        ("Read", "The AI reads the result, then decides again", TEAL_SOFT, TEAL, lx, ly),
    ]
    for t, b, fill, stroke, x, y in nodes:
        rbox(c, x, y, 130, 80, fill, None)
        para(c, t, x + 12, y + 70, 106, style(14, True, stroke))
        para(c, b, x + 12, y + 48, 106, style(10.5, color=INK, leading=13.5))
    arrow(c, lx + 136, ly + s - 40, lx + s - 136, ly + s - 40, LINE)       # decide -> approve
    arrow(c, lx + s - 65, ly + s - 86, lx + s - 65, ly + 86, LINE)          # approve -> run
    arrow(c, lx + s - 136, ly + 40, lx + 136, ly + 40, LINE)               # run -> read
    arrow(c, lx + 65, ly + 86, lx + 65, ly + s - 86, LINE)                  # read -> decide

    # the three kinds of tool
    gx = X0 + s + 50
    gw = X1 - gx
    groups = [
        ("Look things up", "my profile  ·  my requests  ·  the course catalogue", TEAL_SOFT, TEAL),
        ("Check the rules", ("one section  ·  every course this term  ·  ask the student a question"
                            "<br/><font color='#5B6470' size='10'>done by a separate helper agent that can only "
                            "read</font>"), GREEN_SOFT, GREEN),
        ("Take action, with approval", ("send the request  ·  enroll  ·  notify the student  ·  "
                                       "save a note"), AMBER_SOFT, AMBER),
    ]
    top, bh, gap = 408, 82, 12
    for i, (t, b, fill, stroke) in enumerate(groups):
        y = top - (i + 1) * bh - i * gap
        rbox(c, gx, y, gw, bh, fill, None)
        c.setFillColor(stroke)
        c.rect(gx, y, 6, bh, stroke=0, fill=1)
        para(c, t, gx + 22, y + bh - 14, gw - 40, style(14, True, stroke))
        para(c, b, gx + 22, y + bh - 38, gw - 40, style(11.5, leading=15))
    para(c, "Built-in safety: the AI can never choose whose data it sees, and only the main assistant can take "
            "action.", gx, top - 3 * bh - 2 * gap - 14, gw, style(11, color=GREY))


# ------------------------------------------------------------------------------------------------- slide 4

def slide_decisions(c):
    header(c, 4, "Key decisions", "What we chose, and why",
           "Each decision is written up with its reasons and the alternatives in our design log.")
    decisions = [
        ("Safety lives in code", "Approvals use signed, single-use passes that the AI itself cannot create."),
        ("People stay in control", ("Nothing is sent without the student, and nothing is enrolled without the "
                                   "instructor.")),
        ("Checked three times", ("Eligibility is checked again when the request is made, submitted and "
                                "carried out.")),
        ("Nothing gets lost", "Requests survive a restart, and every change is logged."),
        ("A helper agent for checks", ("A separate checker keeps the main assistant focused, and it can only "
                                      "read.")),
        ("A free, swappable AI model", ("gpt-oss-120b on Databricks Free Edition. The model is a setting, "
                                       "not code.")),
    ]
    cw, ch, gx, gy = (X1 - X0 - 2 * 16) / 3, 96, 16, 14
    for i, (t, b) in enumerate(decisions):
        col, row = i % 3, i // 3
        x = X0 + col * (cw + gx)
        top = 404 - row * (ch + gy)
        rbox(c, x, top - ch, cw, ch, WHITE, LINE)
        disc(c, x + 26, top - 26, 13, TEAL, str(i + 1), 12)
        para(c, t, x + 48, top - 18, cw - 60, style(13.5, True, NAVY))
        para(c, b, x + 18, top - 48, cw - 36, style(11, color=INK, leading=14.5))

    # headline numbers
    stats = [("M0–M9", "milestones complete"), ("218", "automated tests passing"),
             ("50", "course sections to test with"), ("2", "human approvals per request")]
    sw_ = (X1 - X0 - 3 * 16) / 4
    for i, (big, small) in enumerate(stats):
        x = X0 + i * (sw_ + 16)
        rbox(c, x, 50, sw_, 74, NAVY, None)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(x + sw_ / 2, 90, big)
        c.setFillColor(colors.HexColor("#CFE3E8"))
        c.setFont("Helvetica", 11)
        c.drawCentredString(x + sw_ / 2, 66, small)
    assert all(stringWidth(s, "Helvetica", 11) < sw_ - 10 for _, s in stats)


def main() -> None:
    c = canvas.Canvas(OUT, pagesize=(W, H))
    c.setTitle("LUMS Process Orchestrator")
    c.setAuthor("Group 4, SProj 2026-27")
    for slide in (slide_what, slide_flow, slide_tools, slide_decisions):
        slide(c)
        c.showPage()
    c.save()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
