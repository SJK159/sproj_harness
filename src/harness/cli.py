"""Student chat loop.

    uv run python -m harness.cli --student S1
    uv run python -m harness.cli --student S1 --message "can i get force enrolled in CS412?"
"""

import argparse
import json
import secrets

from langchain_core.messages import AIMessage

from harness.agent import build_agent
from harness.config import load_env
from harness.context import HarnessContext
from harness.persistence import open_checkpointer


def _show_turn(messages: list, start: int) -> None:
    for m in messages[start:]:
        if isinstance(m, AIMessage):
            for c in m.tool_calls:
                print(f"  -> {c['name']}({json.dumps(c['args'], ensure_ascii=False)[:160]})")
    print(f"\nassistant: {messages[-1].text}\n")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Chat with the force-enrollment assistant as a student.")
    parser.add_argument("--student", required=True, help="student ID from the mock data, e.g. S1")
    parser.add_argument("--message", help="send one message and exit")
    args = parser.parse_args()

    agent = build_agent(checkpointer=open_checkpointer())
    thread_id = f"chat-{args.student}-{secrets.token_hex(4)}"
    config = {"configurable": {"thread_id": thread_id}, "run_name": "student-chat", "tags": ["cli", args.student]}
    context = HarnessContext(student_id=args.student)
    print(f"student {args.student}, thread {thread_id}")

    seen = 0
    while True:
        text = args.message if args.message else input("you: ").strip()
        if not text or text.lower() in {"exit", "quit"}:
            return
        result = agent.invoke({"messages": [{"role": "user", "content": text}]}, config=config, context=context)
        _show_turn(result["messages"], seen)
        seen = len(result["messages"])
        if args.message:
            return


if __name__ == "__main__":
    main()
