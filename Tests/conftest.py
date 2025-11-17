import pytest

from src.user_state_service import UserStateManager


@pytest.fixture(autouse=True)
def isolate_user_state_manager(tmp_path, monkeypatch):
    """Provide isolated user state storage for tests."""
    base_dir = tmp_path / "user_states"
    manager = UserStateManager(base_dir=str(base_dir))

    # Patch globals in modules that keep a singleton instance
    monkeypatch.setattr("src.user_state_service.user_state_manager", manager, raising=False)
    monkeypatch.setattr("src.user_management_service.user_state_manager", manager, raising=False)

    return manager
