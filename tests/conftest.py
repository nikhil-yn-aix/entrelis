"""shared fixtures: hypothesis profiles and per-worker falkordb graphs."""

import os
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from falkordb.asyncio import FalkorDB
from falkordb.asyncio.graph import AsyncGraph
from hypothesis import settings as hypothesis_settings
from pydantic import SecretStr
from redis.exceptions import RedisError

from entrelis.config import Settings

for _name, _examples in (("check", 50), ("slow", 500)):
    hypothesis_settings.register_profile(
        _name, max_examples=_examples, deadline=None, derandomize=True, database=None
    )
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "check"))


@pytest.fixture(scope="session")
def settings() -> Settings:
    """process settings from the environment."""
    return Settings()


async def _connect(settings: Settings, username: str | None, password: SecretStr) -> FalkorDB:
    """open a falkordb client for one user and fail in plain words when it cannot connect."""
    url = urlparse(settings.falkordb_url)
    try:
        client = FalkorDB(
            host=url.hostname or "localhost",
            port=url.port or 6379,
            username=username,
            password=password.get_secret_value() or None,
            socket_connect_timeout=2,
        )
        await client.connection.ping()
    except (RedisError, OSError) as error:
        failure = str(error).rstrip(".")
    else:
        return client
    pytest.fail(
        f"falkordb not reachable at {settings.falkordb_url}: {failure}. "
        "start it with `docker compose up -d --wait falkordb`",
        pytrace=False,
    )


async def _drop(graph: AsyncGraph) -> None:
    """delete a test graph and fail in plain words when the server is gone."""
    try:
        await graph.delete()
    except (RedisError, OSError) as error:
        pytest.fail(f"falkordb went away before {graph.name} was deleted: {error}", pytrace=False)


@pytest_asyncio.fixture(scope="session")
async def falkordb_admin(settings: Settings) -> AsyncIterator[FalkorDB]:
    """session client as the default user, for admin commands only."""
    client = await _connect(settings, None, settings.falkordb_password)
    yield client
    await client.connection.aclose()


@pytest_asyncio.fixture(scope="session")
async def falkordb_client(settings: Settings) -> AsyncIterator[FalkorDB]:
    """session client as the rw acl user."""
    client = await _connect(settings, "rw", settings.falkordb_rw_password)
    yield client
    await client.connection.aclose()


@pytest_asyncio.fixture(scope="session")
async def template_graph(falkordb_client: FalkorDB, worker_id: str) -> AsyncIterator[AsyncGraph]:
    """an empty graph per xdist worker that every test graph is copied from."""
    template = falkordb_client.select_graph(f"test:{worker_id}:template")
    await template.query("CREATE (n:Seed) DELETE n")
    yield template
    await _drop(template)


@pytest_asyncio.fixture
async def graph(template_graph: AsyncGraph, worker_id: str) -> AsyncIterator[AsyncGraph]:
    """a private copy of the template graph, deleted after the test."""
    copy = await template_graph.copy(f"test:{worker_id}:{uuid.uuid4().hex}")
    yield copy
    await _drop(copy)
