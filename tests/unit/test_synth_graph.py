"""the seeded synthetic tenant is deterministic, sized to target and shaped like a company graph."""

from collections import Counter, defaultdict
from functools import cache
from statistics import median

import pytest

from eval.data.synth_graph import (
    EDGE_CYPHER,
    NODE_CYPHER,
    Tenant,
    generate,
)

ITEM_LABELS = ("Doc", "Ticket", "PR", "Commit", "Answer", "Step", "Memory", "Message")
ACTOR_LABELS = ("Person", "Agent")
TARGET = 12_000


@cache
def tenant(seed: int = 7, edges: int = TARGET) -> Tenant:
    return generate(seed=seed, edges=edges)


def node_ids(t: Tenant, *labels: str) -> set[str]:
    return {row["id"] for label in labels for row in t.nodes[label]}


def link_structure(t: Tenant) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    premises: dict[str, list[str]] = defaultdict(list)
    for group in ("PREMISE:Fact", "PREMISE:Item"):
        for row in t.edges[group]:
            premises[row["src"]].append(row["dst"])
    links_of: dict[str, list[str]] = defaultdict(list)
    for row in t.edges["SUPPORTS"]:
        links_of[row["dst"]].append(row["src"])
    return premises, links_of


def depths(t: Tenant) -> dict[str, int]:
    premises, links_of = link_structure(t)
    memo: dict[str, int] = dict.fromkeys(node_ids(t, "Fact"), 0)

    def depth(node: str) -> int:
        if node not in memo:
            memo[node] = min(1 + max(depth(p) for p in premises[link]) for link in links_of[node])
        return memo[node]

    return {item: depth(item) for item in links_of}


def test_same_seed_gives_identical_batches() -> None:
    first = list(generate(seed=3, edges=3_000).batches(500))
    second = list(generate(seed=3, edges=3_000).batches(500))
    assert first == second


def test_different_seeds_differ() -> None:
    a = generate(seed=3, edges=3_000)
    b = generate(seed=4, edges=3_000)
    assert a.nodes["Fact"] != b.nodes["Fact"]
    assert a.edges["PREMISE:Fact"] != b.edges["PREMISE:Fact"]


@pytest.mark.parametrize("target", [5_000, 12_000, 20_000, 100_000])
def test_edge_count_lands_exactly_on_target(target: int) -> None:
    assert generate(seed=11, edges=target).edge_count() == target


def test_batches_respect_size_and_cover_every_row() -> None:
    t = tenant()
    batches = list(t.batches(250))
    assert all(0 < len(batch.rows) <= 250 for batch in batches)
    assert sum(len(b.rows) for b in batches if b.name in EDGE_CYPHER) == t.edge_count()
    assert sum(len(b.rows) for b in batches if b.name in NODE_CYPHER) == t.node_count()
    assert all(batch.cypher.startswith("UNWIND $rows AS r") for batch in batches)


def test_nodes_come_before_edges_in_load_order() -> None:
    names = [batch.name for batch in tenant().batches(1000)]
    last_node = max(i for i, n in enumerate(names) if n in NODE_CYPHER)
    first_edge = min(i for i, n in enumerate(names) if n in EDGE_CYPHER)
    assert last_node < first_edge


def test_rows_hold_only_primitives_and_ids_are_unique() -> None:
    t = tenant()
    seen: set[str] = set()
    for rows in t.nodes.values():
        for row in rows:
            assert all(v is None or isinstance(v, str | int) for v in row.values())
            assert row["id"] not in seen
            seen.add(row["id"])
    for rows in t.edges.values():
        for row in rows:
            assert all(v is None or isinstance(v, str | int) for v in row.values())


def test_every_edge_endpoint_exists_with_the_right_label() -> None:
    t = tenant()
    ends = {
        "PREMISE:Fact": (("Link",), ("Fact",)),
        "PREMISE:Item": (("Link",), ITEM_LABELS),
        "SUPPORTS": (("Link",), ITEM_LABELS),
        "DEPENDS_ON:Fact": (ITEM_LABELS, ("Fact",)),
        "DEPENDS_ON:Item": (ITEM_LABELS, ITEM_LABELS),
        "READ:Fact": (ITEM_LABELS, ("Fact",)),
        "READ:Item": (ITEM_LABELS, ITEM_LABELS),
        "OWNED_BY:Fact": (("Fact",), ACTOR_LABELS),
        "OWNED_BY:Item": (ITEM_LABELS, ACTOR_LABELS),
        "REPORTS_TO": (ACTOR_LABELS, ACTOR_LABELS),
    }
    assert set(ends) == set(t.edges)
    for group, (src_labels, dst_labels) in ends.items():
        src = node_ids(t, *src_labels)
        dst = node_ids(t, *dst_labels)
        for row in t.edges[group]:
            assert row["src"] in src, group
            assert row["dst"] in dst, group


def test_entities_carry_the_documented_properties() -> None:
    t = tenant()
    assert set(t.nodes["Fact"][0]) == {
        "id",
        "s",
        "p",
        "o",
        "text",
        "kind",
        "valid_from",
        "valid_to",
        "learned_at",
        "died_learned_at",
        "status",
        "durability",
        "last_confirmed",
        "hash",
    }
    assert set(t.nodes["Link"][0]) == {"id", "rule", "kind", "created_at"}
    assert set(t.nodes["Person"][0]) == {"id", "handle", "active_from", "active_to"}
    item = next(row for label in ITEM_LABELS for row in t.nodes[label])
    assert set(item) == {"id", "uri", "title", "created_at", "status", "hash"}
    assert {row["kind"] for row in t.nodes["Link"]} == {"hard", "soft"}


def test_content_reads_like_a_company_not_a_toy() -> None:
    t = tenant()
    texts = [row["text"] for row in t.nodes["Fact"]]
    assert any("is owned by" in text for text in texts)
    assert any("reads from postgres" in text for text in texts)
    assert any("deprecated" in text for text in texts)
    assert len(set(texts)) > len(texts) * 0.9
    handles = [row["handle"] for row in t.nodes["Person"]]
    assert len(set(handles)) == len(handles)
    blob = " ".join(texts + handles).lower()
    assert "foo" not in blob
    assert "bar" not in blob.replace("barrier", "")


def test_times_are_utc_ms_within_about_180_days() -> None:
    t = tenant()
    stamps = [r["created_at"] for label in ITEM_LABELS for r in t.nodes[label]]
    stamps += [r["learned_at"] for r in t.nodes["Fact"]]
    stamps += [r["at"] for r in t.edges["READ:Fact"]]
    span_days = (max(stamps) - min(stamps)) / 86_400_000
    assert 120 <= span_days <= 200
    assert all(isinstance(s, int) and s > 1_500_000_000_000 for s in stamps)


def test_a_few_facts_are_already_dead() -> None:
    facts = tenant().nodes["Fact"]
    dead = [f for f in facts if f["status"] == "dead"]
    assert 0 < len(dead) < len(facts) * 0.1
    assert all(f["valid_to"] is not None and f["died_learned_at"] is not None for f in dead)
    live = [f for f in facts if f["status"] != "dead"]
    assert all(f["valid_to"] is None for f in live)


def test_most_items_sit_one_to_three_hops_from_base_facts_with_some_deep_chains() -> None:
    d = depths(tenant())
    counts = Counter(d.values())
    near = sum(n for depth, n in counts.items() if 1 <= depth <= 3)
    assert near / len(d) > 0.6
    assert sum(n for depth, n in counts.items() if depth >= 6) >= 5
    assert min(d.values()) == 1


def test_a_noticeable_share_of_items_have_alternative_supports() -> None:
    _, links_of = link_structure(tenant())
    share = sum(1 for links in links_of.values() if len(links) >= 2) / len(links_of)
    assert 0.05 <= share <= 0.20


def test_links_have_one_to_three_premises_and_exactly_one_target() -> None:
    t = tenant()
    premises, _ = link_structure(t)
    assert set(premises) == node_ids(t, "Link")
    assert {len(p) for p in premises.values()} == {1, 2, 3}
    assert all(len(set(p)) == len(p) for p in premises.values())
    targets = Counter(row["src"] for row in t.edges["SUPPORTS"])
    assert set(targets.values()) == {1}


def test_depends_on_is_derived_from_link_premises() -> None:
    t = tenant()
    premises, links_of = link_structure(t)
    expected = {
        (item, premise)
        for item, links in links_of.items()
        for link in links
        for premise in premises[link]
    }
    actual = {
        (r["src"], r["dst"])
        for group in ("DEPENDS_ON:Fact", "DEPENDS_ON:Item")
        for r in t.edges[group]
    }
    assert actual == expected
    assert sum(len(t.edges[g]) for g in ("DEPENDS_ON:Fact", "DEPENDS_ON:Item")) == len(expected)


def test_a_few_hub_facts_dominate_fan_in() -> None:
    t = tenant()
    fan_in = Counter(dict.fromkeys(node_ids(t, "Fact"), 0))
    fan_in.update(row["dst"] for row in t.edges["PREMISE:Fact"])
    assert max(fan_in.values()) >= 20 * max(1.0, median(fan_in.values()))


def test_every_fact_and_item_has_one_owner_and_actors_form_a_forest() -> None:
    t = tenant()
    owned = Counter(r["src"] for g in ("OWNED_BY:Fact", "OWNED_BY:Item") for r in t.edges[g])
    assert set(owned) == node_ids(t, "Fact", *ITEM_LABELS)
    assert set(owned.values()) == {1}
    boss = {r["src"]: r["dst"] for r in t.edges["REPORTS_TO"]}
    assert len(boss) == len(t.edges["REPORTS_TO"])
    for actor in boss:
        seen = {actor}
        while actor in boss:
            actor = boss[actor]
            assert actor not in seen
            seen.add(actor)


def test_reads_carry_a_session_id() -> None:
    reads = tenant().edges["READ:Fact"]
    assert reads
    assert all(r["session"].startswith("sess-") for r in reads)


def test_every_group_has_load_cypher() -> None:
    t = tenant()
    assert set(t.nodes) <= set(NODE_CYPHER)
    assert set(t.edges) <= set(EDGE_CYPHER)


def test_reads_never_happen_before_the_reader_or_the_target_exists() -> None:
    t = tenant()
    born = {r["id"]: r["created_at"] for label in ITEM_LABELS for r in t.nodes[label]}
    born |= {r["id"]: r["learned_at"] for r in t.nodes["Fact"]}
    for group in ("READ:Fact", "READ:Item"):
        for r in t.edges[group]:
            assert r["at"] >= born[r["src"]], group
            assert r["at"] >= born[r["dst"]], group
