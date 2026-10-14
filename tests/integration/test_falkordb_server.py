"""the running falkordb matches the pinned image and supports fulltext search on facts."""

import asyncio
import re
from pathlib import Path
from typing import Any, cast

import pytest
from falkordb.asyncio import FalkorDB
from falkordb.asyncio.graph import AsyncGraph

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yaml"
IMAGE_LINE = re.compile(r"image:\s*falkordb/falkordb:(\d+)\.(\d+)\.(\d+)")


def compose_version() -> tuple[int, int, int]:
    """semver of the falkordb image pinned in compose.yaml."""
    if not COMPOSE.exists():
        pytest.fail(f"compose.yaml not found at {COMPOSE}", pytrace=False)
    match = IMAGE_LINE.search(COMPOSE.read_text())
    if match is None:
        pytest.fail("compose.yaml has no falkordb/falkordb image line with a semver", pytrace=False)
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


async def graph_module_version(admin: FalkorDB) -> int:
    """integer version the server reports for its graph module."""
    modules = cast(list[dict[str, Any]], await admin.execute_command("MODULE LIST"))
    for module in modules:
        if module["name"] == "graph":
            return int(module["ver"])
    pytest.fail("the server has no graph module", pytrace=False)


async def wait_for_indexes(graph: AsyncGraph) -> None:
    """poll the index list until every index is operational."""
    for _ in range(100):
        result = await graph.query("CALL db.indexes() YIELD status RETURN status")
        if all(row[0] == "OPERATIONAL" for row in result.result_set):
            return
        await asyncio.sleep(0.02)
    pytest.fail("indexes did not become operational in time", pytrace=False)


async def test_graph_module_version_matches_the_pinned_image(falkordb_admin: FalkorDB) -> None:
    major, minor, patch = compose_version()
    assert await graph_module_version(falkordb_admin) == major * 10_000 + minor * 100 + patch


async def test_fulltext_index_finds_facts_by_word(graph: AsyncGraph) -> None:
    await graph.query("CREATE FULLTEXT INDEX FOR (n:Fact) ON (n.text)")
    await wait_for_indexes(graph)
    await graph.query(
        "CREATE (:Fact {id: $a, text: $at}), (:Fact {id: $b, text: $bt})",
        {
            "a": "fact-00001",
            "at": "billing-api v2 is owned by payments",
            "b": "fact-00002",
            "bt": "orders-service reads from postgres 14",
        },
    )
    result = await graph.query(
        "CALL db.idx.fulltext.queryNodes('Fact', 'billing') YIELD node RETURN node.text"
    )
    assert [row[0] for row in result.result_set] == ["billing-api v2 is owned by payments"]
