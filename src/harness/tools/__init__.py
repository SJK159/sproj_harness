"""Agent tools. Names used by the tool-visibility checks (CLAUDE.md invariant 9)."""

# Tools that change a case or an enrollment. Main agent only (M5), never on a sub-agent.
WRITE_TOOL_NAMES = frozenset({"submit_case", "execute_enrollment", "notify_student"})

# deepagents' built-in file tools that write or run commands. Sub-agents get none of them.
FILE_WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "delete", "execute"})
