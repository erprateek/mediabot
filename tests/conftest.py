import pytest

from src.db.database import Database


@pytest.fixture
def tmp_db(tmp_path):
    return Database(db_file=str(tmp_path / "test.db"))
