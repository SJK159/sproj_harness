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