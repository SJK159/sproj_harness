import os
import re

import pytest
from langchain_core.messages import AIMessage

from harness.agent import build_agent
from harness.config import load_env
from harness.context import HarnessContext

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="live model test; set RUN_LIVE=1")]


def test_m3_done_when(seeded):
    load_env()
    result = build_agent().invoke(
        {"messages": [{"role": "user", "content": "can i get force enrolled in CS412?"}]},
        context=HarnessContext(student_id="S1"),
        config={"run_name": "m3-done-when", "tags": ["m3"]},
    )
    calls = [c for m in result["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
    names = [c["name"] for c in calls]
    assert "write_todos" in names
    assert any(c["name"] == "read_file" and "force-enrollment/SKILL.md" in c["args"].get("file_path", "") for c in calls)
    assert "check_my_eligibility" in names
    # gpt-oss writes typographic hyphens (U+2011 etc.) in labels like "FE‑1"; treat them as "-".
    answer = re.sub("[‐-―−]", "-", result["messages"][-1].text)
    assert re.search(r"FE-\d \(placeholder v0\.1\)", answer), answer