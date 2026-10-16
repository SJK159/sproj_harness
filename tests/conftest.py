import pytest
from harness.mock_zambeel import connect, init_schema, seed

@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "harness.db")
    init_schema(conn)
    seed(conn)
    yield conn
    conn.close()