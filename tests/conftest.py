import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_test_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use isolated DB and reset counters for deterministic tests."""
    monkeypatch.setenv("INVENTORY_DB_PATH", str(tmp_path / "test_inventory.sqlite3"))

    from src import app as app_module

    app_module.REQUEST_COUNT = 0
