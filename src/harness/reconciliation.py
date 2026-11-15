"""Close a stale instructor pause after canonical worker completion, without LLM calls.

Only authoritative terminal case records may supply the saved tool outcome. This
does not approve a tool, mint a token or perform enrollment. Requires the shared
FE case DB deployment; BFF reads first authorize the case through FE MCP.
"""
import json
import threading

from langchain_core.messages import AIMessage, ToolMessage

from harness.clients import pending_actions
from harness.memory import FINAL_STATES, append_note, case_note

_lock = threading.RLock()  # Single API process deployment; concurrent reads converge.


def reconcile_finished(conn, agent, store, case_id, student_id):
    with _lock:
        case = conn.execute("SELECT * FROM cases WHERE case_id = ? AND student_id = ?", (case_id, student_id)).fetchone()
        if case is None or case["state"] not in FINAL_STATES or pending_actions(agent, case_id) != ["execute_enrollment"]:
            return False
        config = {"configurable":{"thread_id":case_id}}
        state = agent.get_state(config)
        last = next((m for m in reversed(state.values.get("messages", [])) if isinstance(m, AIMessage)), None)
        if last is None or len(last.tool_calls) != 1 or last.tool_calls[0]["name"] != "execute_enrollment":
            return False
        if case["state"] == "COMPLETED":
            enrolled = conn.execute("SELECT enrollment_id FROM enrollments WHERE idempotency_key = ?", (case_id,)).fetchone()
            if enrolled is None:
                raise RuntimeError("Completed case has no saved enrollment; manual reconciliation required")
            outcome = {"case_id":case_id, "state":"COMPLETED", "enrollment_id":enrolled[0]}
        else:
            outcome = {"case_id":case_id, "state":case["state"]}
        # Public graph inspection rather than assuming private middleware names.
        ends = {edge.source for edge in agent.get_graph().edges if edge.target == "__end__" and not edge.conditional}
        if len(ends) != 1:
            raise RuntimeError("Agent graph changed; terminal reconciliation requires review")
        text = f"Case {case_id} for {case['offering_id']} is {case['state']}. This outcome was recovered from the saved case record."
        # Notes are idempotent. Write before checkpoint closure so a crash between
        # the stores simply retries the same case-derived note.
        append_note(store, student_id, case_id, case_note(conn, dict(case)))
        agent.update_state(config, {"messages":[
            ToolMessage(content=json.dumps(outcome), tool_call_id=last.tool_calls[0]["id"], name="execute_enrollment"),
            AIMessage(content=text),
        ]}, as_node=next(iter(ends)))
        return True
