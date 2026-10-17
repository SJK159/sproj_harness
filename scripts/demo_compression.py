"""Context-compression demo: one long, messy student conversation with low thresholds (live model).

Demo mode (harness.agent.build_agent(compression="demo")) summarizes the conversation past 12,000 tokens
(keeping the last 10 messages) and offloads any tool result over 300 tokens to /large_tool_results/.
The default mode uses the model's real 128K window. Nothing is submitted (confirmation answer: no).
Each turn is traced in LangSmith; find them by the printed thread id. Every run is capped at 25 model calls.

    uv run python scripts/demo_compression.py
"""

import secrets

from langchain_core.messages.utils import count_tokens_approximately

from harness.agent import (
    DEMO_EVICT_TOKENS,
    DEMO_KEEP_MESSAGES,
    DEMO_TRIGGER_TOKENS,
    build_agent,
)
from harness.clients import student_turn
from harness.config import load_env
from harness.persistence import open_checkpointer

PASTED = (
    "ok so context: this semester is chaos. I have a part-time job on tuesdays and thursdays, my hostel wifi "
    "drops every evening, I'm in two societies, and my group project partner vanished. Here is my whole week: "
) + " ".join(f"day {d}: lectures, lab, society meeting, gym, readings for course {c};" for d in range(1, 8)
              for c in ("HUM101", "SS101", "ECON100", "PHIL101", "BIO100")) * 2

MESSAGES = [
    "hey so um i was wondering abt force enrollment, whats the deal with it",
    "can i get into the machine learning course? sec 1 i think",
    PASTED + " anyway. sorry for the wall of text",
    "wait actually what about CS360 instead",
    "nvm. and CS471? oh and that CS999 special topics thing",
    "how many credits am i taking rn btw",
    "ok can you recap everything we talked about and what i can actually do?",
]


def main() -> None:
    load_env()
    agent = build_agent(checkpointer=open_checkpointer(), compression="demo")
    case_id = f"FE-demo-{secrets.token_hex(3)}"
    config = {"configurable": {"thread_id": case_id}}
    print(f"thread {case_id}: summarize past {DEMO_TRIGGER_TOKENS} tokens keeping the last {DEMO_KEEP_MESSAGES} "
          f"messages; offload tool results over {DEMO_EVICT_TOKENS} tokens\n")
    for i, text in enumerate(MESSAGES, 1):
        turn = student_turn(agent, case_id, "S1", text, confirm=lambda s: False, ask=lambda q: "CS412")
        values = agent.get_state(config).values
        files = sorted(values.get("files", {}))
        event = values.get("_summarization_event")
        print(f"turn {i}: {len(text):>5} chars in | messages {len(values['messages']):>3} | "
              f"~{count_tokens_approximately(values['messages']):>6} tokens in state | "
              f"summarized: {'yes' if event else 'no'}")
        for f in files:
            if f.startswith(("/large_tool_results/", "/conversation_history/")):
                print(f"         file: {f}")
        print(f"         reply: {turn.reply[:160].replace(chr(10), ' ')}")
    print(f"\nLangSmith: filter project sproj-harness by thread {case_id}")


if __name__ == "__main__":
    main()
