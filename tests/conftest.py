import pytest

from harness.mock_zambeel import connect, init_schema, seed


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "harness.db")
    init_schema(conn)
    seed(conn)
    yield conn
    conn.close()

@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("APPROVAL_SECRET", "test-secret-" + "x" * 32)

@pytest.fixture
def awaiting(db):
    """Two cases waiting on their instructor: C-A1 (S1, CS412-S1, owner I1), C-A2 (S2, CS360-S1, owner I1)."""
    for case_id, student, offering in [("C-A1", "S1", "CS412-S1"), ("C-A2", "S2", "CS360-S1")]:
        db.execute(
            "INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
            " VALUES (?, ?, ?, 'FORCE_ENROLLMENT', 'AWAITING_APPROVAL', 'now', 'now')",
            (case_id, student, offering),
        )
    db.commit()
    return db

@pytest.fixture
def seeded(db, tmp_path, monkeypatch):
    """Point the agent's tools (which open their own connections) at the seeded test DB."""
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_STORE", str(tmp_path / "store.db"))
    return db

@pytest.fixture
def flow(seeded, tmp_path, secret):
    """Seeded DB + a checkpoint file. Each agent() call opens a NEW SqliteSaver connection,
    so a resume after a pause runs as if in a fresh process."""
    from harness.agent import build_agent
    from harness.persistence import open_checkpointer

    class Flow:
        db = seeded

        def agent(self, model):
            return build_agent(model=model, checkpointer=open_checkpointer(tmp_path / "checkpoints.db"))

        def store(self):
            from harness.persistence import open_store
            return open_store(tmp_path / "store.db")

    return Flow()
