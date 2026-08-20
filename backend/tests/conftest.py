import pytest

from app.database import engine


@pytest.fixture(autouse=True)
async def dispose_engine_between_tests():
    """Return the shared engine's pooled connections after every test.

    `app.database.engine` is created once at import time, but pytest-asyncio
    runs each test in its own event loop (`asyncio_default_fixture_loop_scope
    = "function"` in pyproject.toml). asyncpg binds a connection to the loop
    that opened it, so the second DB-touching test in a module would otherwise
    pull a connection from the pool belonging to the *previous* test's
    now-closed loop and fail with "Event loop is closed".

    Autouse rather than opt-in: the failure appears only once a module has two
    DB-touching tests, so a future test would hit it as a confusing, unrelated
    error rather than an obvious missing fixture.
    """
    yield
    await engine.dispose()
