from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def settings() -> Settings:
    """Settings built from defaults only — never from the developer's real .env."""
    return Settings(_env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)

    # get_settings() is lru_cached and read via Depends, so it has to be overridden
    # rather than passed — otherwise routes would pick up the ambient environment.
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
