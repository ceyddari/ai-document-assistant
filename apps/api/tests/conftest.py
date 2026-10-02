from unittest.mock import MagicMock

import pytest

from app.api.dependencies import require_organization_member
from app.main import app
from app.models import OrganizationMembership


@pytest.fixture(autouse=True)
def bypass_organization_authorization_for_existing_route_tests():
    app.dependency_overrides[require_organization_member] = lambda: MagicMock(
        spec=OrganizationMembership
    )
    yield
    app.dependency_overrides.pop(require_organization_member, None)
