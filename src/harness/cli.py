"""Student chat. Each session is one thread whose id is the case_id it may create (one case per thread).

    uv run python -m harness.cli --student S1
    uv run python -m harness.cli --student S1 --yes --message "force enroll me in CS412 section S1"
    uv run python -m harness.cli --student S1 --session FE-1a2b3c4d     # continue a session
"""

import argparse
import json
import secrets
from contextlib import closing

from langchain_core.messages import AIMessage

from harness.agent import build_agent
from harness.clients import student_turn
from harness.config import load_env
from harness.mock_zambeel import connect
from harness.notifications import mark_read, unread
from harness.persistence import open_checkpointer


def _show_notices(student_id: str) -> None:
    with closing(connect()) as conn:
        notes = unread(conn, student_id)
        for n in notes:
            print(f"[notice] {n['created_at']} {n['message']}")
        mark_read(conn, [n["notification_id"] for n in notes])


def _show_tool_calls(agent, case_id: str, seen: int) -> int:
    messages = agent.get_state({"configurable": {"thread_id": case_id}}).values.get("messages", [])
    for m in messages[seen:]:
        if isinstance(m, AIMessage):
            for c in m.tool_calls:
                print(f"  -> {c['name']}({json.dumps(c['args'], ensure_ascii=False)[:160]})")
    return len(messages)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Chat with the force-enrollment assistant as a student.")
    parser.add_argument("--student", required=True, help="student ID from the mock data, e.g. S1")
    parser.add_argument("--message", help="send one message and exit")
    parser.add_argument("--session", help="continue an existing session (its case id, e.g. FE-1a2b3c4d)")
    answer = parser.add_mutually_exclusive_group()
    answer.add_argument("--yes", action="store_true", help="answer yes to the submission confirmation (scripted runs)")
    answer.add_argument("--no", action="store_true", help="answer no to the submission confirmation (scripted runs)")
    parser.add_argument("--answer", help="answer to give if the eligibility checker asks a question (scripted runs)")
    args = parser.parse_args()

    def confirm(summary: dict) -> bool:
        if args.yes or args.no:
            print(f"[confirm] submit {summary['offering_id']} as case {summary['case_id']}? {'yes' if args.yes else 'no'}")
            return args.yes
        return input(f"[confirm] Submit a force-enrollment request for {summary['offering_id']} "
                     f"(case {summary['case_id']})? [y/N] ").strip().lower() in {"y", "yes"}

    def ask(question: str) -> str:
        if args.answer is not None:
            print(f"[checker asks] {question} -> {args.answer}")
            return args.answer
        return input(f"[checker asks] {question} ").strip()

    _show_notices(args.student)
    agent = build_agent(checkpointer=open_checkpointer())
    case_id = args.session or f"FE-{secrets.token_hex(4)}"
    print(f"student {args.student}, session {case_id}")

    # a continued session only prints tool calls made from now on
    seen = len(agent.get_state({"configurable": {"thread_id": case_id}}).values.get("messages", []))
    while True:
        try:
            text = args.message if args.message else input("you: ").strip()
        except EOFError:  # piped input ended
            return
        if not text or text.lower() in {"exit", "quit"}:
            return
        turn = student_turn(agent, case_id, args.student, text, confirm, ask)
        seen = _show_tool_calls(agent, case_id, seen)
        if turn.reply:
            print(f"\nassistant: {turn.reply}\n")
        if turn.status == "waiting_for_instructor":
            print(f"Case {case_id} is waiting for the instructor. You will see the outcome as a notice next time.")
            return
        if args.message:
            return


if __name__ == "__main__":
    main()
