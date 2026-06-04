import pytest

from app.platform.config import get_settings
from app.platform.db.session import _engine, _sessionmaker


@pytest.fixture(autouse=True)
def reset_caches():
    get_settings.cache_clear()
    _engine.cache_clear()
    _sessionmaker.cache_clear()
    yield
    get_settings.cache_clear()
    _engine.cache_clear()
    _sessionmaker.cache_clear()
