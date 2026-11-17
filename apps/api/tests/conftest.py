from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.dependencies import require_organization_member
from app.main import app
from app.models import OrganizationMembership


@pytest.fixture(autouse=True)
def skip_startup_database_work(monkeypatch: pytest.MonkeyPatch) -> None:
    # `with TestClient(app)` runs the lifespan; keep it away from the real database.
    monkeypatch.setattr("app.main.fail_interrupted_documents", AsyncMock(return_value=0))


@pytest.fixture(autouse=True)
def bypass_organization_authorization_for_existing_route_tests():
    app.dependency_overrides[require_organization_member] = lambda: MagicMock(
        spec=OrganizationMembership
    )
    yield
    app.dependency_overrides.pop(require_organization_member, None)
