"""a 100k edge synthetic tenant loads into falkordb with every relationship intact."""

import time

from falkordb.asyncio.graph import AsyncGraph

from eval.data.synth_graph import generate, load


async def test_100k_edge_tenant_loads_with_matching_edge_count(graph: AsyncGraph) -> None:
    tenant = generate(seed=7, edges=100_000)
    started = time.perf_counter()
    await load(graph, tenant)
    elapsed = time.perf_counter() - started
    print(f"loaded {tenant.node_count()} nodes and {tenant.edge_count()} edges in {elapsed:.1f}s")
    edges = await graph.query("MATCH ()-[r]->() RETURN count(r)")
    nodes = await graph.query("MATCH (n) RETURN count(n)")
    assert edges.result_set[0][0] == tenant.edge_count()
    assert nodes.result_set[0][0] == tenant.node_count()
