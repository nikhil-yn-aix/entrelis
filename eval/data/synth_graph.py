"""seeded generator of one synthetic company tenant, with unwind-ready batches and load cypher."""

import asyncio
import hashlib
import random
from bisect import bisect
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import accumulate
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from falkordb.asyncio.graph import AsyncGraph

Row = dict[str, Any]

START_MS = 1_767_225_600_000
DAY_MS = 86_400_000
WINDOW_DAYS = 180

ITEM_LABELS = ("Doc", "Ticket", "PR", "Commit", "Answer", "Step", "Memory", "Message")
DEPTH_WEIGHTS = (0.56, 0.20, 0.12, 0.05, 0.03, 0.02, 0.015, 0.01, 0.005)
EDGES_PER_ITEM = 6.8
STRUCTURE_SHARE = (0.80, 0.97)
ZIPF_EXPONENT = 1.05

TEAMS = (
    "payments",
    "platform",
    "growth",
    "data",
    "security",
    "mobile",
    "infra",
    "search",
    "identity",
    "fulfilment",
)
TEAM_KEYS = ("PAY", "PLT", "GRW", "DAT", "SEC", "MOB", "INF", "SRC", "IDN", "FUL")
DOMAINS = (
    "billing",
    "orders",
    "checkout",
    "catalog",
    "inventory",
    "shipping",
    "notifications",
    "auth",
    "ledger",
    "pricing",
    "recommendations",
    "fraud",
    "analytics",
    "reporting",
    "messaging",
    "media",
    "support",
    "onboarding",
    "loyalty",
    "tax",
    "invoicing",
    "subscriptions",
    "returns",
    "payouts",
    "search",
    "profiles",
    "coupons",
    "refunds",
)
SERVICE_KINDS = ("api", "service", "worker", "gateway", "web", "indexer", "scheduler", "consumer")
DATASTORES = (
    "postgres 14",
    "postgres 15",
    "postgres 16",
    "redis 7",
    "kafka 3.7",
    "mysql 8",
    "elasticsearch 8",
    "clickhouse 24",
    "dynamodb",
    "rabbitmq 3.13",
    "s3",
    "memcached 1.6",
)
RUNTIMES = (
    "python 3.12",
    "go 1.22",
    "node 20",
    "java 21",
    "kubernetes 1.29",
    "kubernetes 1.30",
)
REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-south-1")
FIRST_NAMES = (
    "priya",
    "marcus",
    "elena",
    "tomas",
    "aisha",
    "daniel",
    "mei",
    "rohan",
    "sofia",
    "liam",
    "nadia",
    "kenji",
    "olivia",
    "arjun",
    "hannah",
    "carlos",
    "fatima",
    "jonas",
    "isabel",
    "yusuf",
    "grace",
    "mateo",
    "anika",
    "felix",
    "leila",
    "owen",
    "sana",
    "victor",
    "chloe",
    "dmitri",
    "ines",
    "noah",
    "zara",
    "hugo",
    "tara",
    "emil",
    "maya",
    "luca",
    "rina",
    "ethan",
)
LAST_NAMES = (
    "nair",
    "okafor",
    "petrov",
    "lindqvist",
    "haddad",
    "kowalski",
    "tanaka",
    "iyer",
    "rossi",
    "mbeki",
    "novak",
    "fischer",
    "santos",
    "kaur",
    "dubois",
    "yilmaz",
    "andersen",
    "reyes",
    "chen",
    "volkov",
    "mensah",
    "larsen",
    "gupta",
    "moreau",
    "ibrahim",
    "costa",
    "sato",
    "brennan",
    "ortiz",
    "schmidt",
    "kim",
    "rahman",
    "walsh",
    "pereira",
    "jovanovic",
    "singh",
    "hoang",
    "nielsen",
    "adeyemi",
    "marin",
)
AGENT_HANDLES = (
    "claude-code",
    "renovate-bot",
    "dependabot",
    "triage-agent",
    "runbook-agent",
    "release-bot",
    "oncall-agent",
    "docs-sync-agent",
)
LINK_RULES = (
    "owner-inference",
    "version-pin",
    "dependency-match",
    "runbook-derivation",
    "deprecation-propagation",
    "oncall-routing",
)
ACTIONS = (
    "migrate",
    "upgrade",
    "document",
    "add retries to",
    "rate limit",
    "split",
    "audit",
    "load test",
    "decommission",
    "add tracing to",
)
TOPICS = ("rollback", "failover", "capacity plan", "on-call handoff", "incident response", "slo")
FACT_KINDS = {
    "owned_by": "ownership",
    "reads_from": "dependency",
    "oncall": "rotation",
    "deprecated_on": "deprecation",
    "latency_slo": "slo",
    "runs_on": "runtime",
    "rate_limit": "config",
}
DURABILITY = {
    "ownership": "durable",
    "dependency": "durable",
    "rotation": "volatile",
    "deprecation": "permanent",
    "slo": "durable",
    "runtime": "durable",
    "config": "volatile",
}

FACT_PROPS = (
    "id: r.id, s: r.s, p: r.p, o: r.o, text: r.text, kind: r.kind, valid_from: r.valid_from, "
    "valid_to: r.valid_to, learned_at: r.learned_at, died_learned_at: r.died_learned_at, "
    "status: r.status, durability: r.durability, last_confirmed: r.last_confirmed, hash: r.hash"
)
ITEM_PROPS = (
    "id: r.id, uri: r.uri, title: r.title, created_at: r.created_at, status: r.status, hash: r.hash"
)
ACTOR_PROPS = "id: r.id, handle: r.handle, active_from: r.active_from, active_to: r.active_to"
LINK_PROPS = "id: r.id, rule: r.rule, kind: r.kind, created_at: r.created_at"

NODE_CYPHER: dict[str, str] = {
    "Person": f"UNWIND $rows AS r CREATE (:Actor:Person {{{ACTOR_PROPS}}})",
    "Agent": f"UNWIND $rows AS r CREATE (:Actor:Agent {{{ACTOR_PROPS}}})",
    "Fact": f"UNWIND $rows AS r CREATE (:Fact {{{FACT_PROPS}}})",
    "Link": f"UNWIND $rows AS r CREATE (:Link {{{LINK_PROPS}}})",
    **{
        label: f"UNWIND $rows AS r CREATE (:Item:{label} {{{ITEM_PROPS}}})" for label in ITEM_LABELS
    },
}


def _edge_cypher(rel: str, src: str, dst: str, props: str = "") -> str:
    """cypher creating one relationship type between id-matched endpoints."""
    return (
        f"UNWIND $rows AS r MATCH (a:{src} {{id: r.src}}), (b:{dst} {{id: r.dst}}) "
        f"CREATE (a)-[:{rel}{props}]->(b)"
    )


EDGE_CYPHER: dict[str, str] = {
    "REPORTS_TO": _edge_cypher("REPORTS_TO", "Actor", "Actor", " {`from`: r.since, `to`: r.until}"),
    "OWNED_BY:Fact": _edge_cypher("OWNED_BY", "Fact", "Actor", " {`from`: r.since, `to`: r.until}"),
    "OWNED_BY:Item": _edge_cypher("OWNED_BY", "Item", "Actor", " {`from`: r.since, `to`: r.until}"),
    "PREMISE:Fact": _edge_cypher("PREMISE", "Link", "Fact"),
    "PREMISE:Item": _edge_cypher("PREMISE", "Link", "Item"),
    "SUPPORTS": _edge_cypher("SUPPORTS", "Link", "Item"),
    "DEPENDS_ON:Fact": _edge_cypher("DEPENDS_ON", "Item", "Fact", " {at: r.at, kind: r.kind}"),
    "DEPENDS_ON:Item": _edge_cypher("DEPENDS_ON", "Item", "Item", " {at: r.at, kind: r.kind}"),
    "READ:Fact": _edge_cypher("READ", "Item", "Fact", " {at: r.at, session: r.session}"),
    "READ:Item": _edge_cypher("READ", "Item", "Item", " {at: r.at, session: r.session}"),
}

INDEX_CYPHER = tuple(
    f"CREATE INDEX FOR (n:{label}) ON (n.id)" for label in ("Fact", "Item", "Link", "Actor")
)
INDEX_LIST_CYPHER = "CALL db.indexes() YIELD status RETURN status"


@dataclass(frozen=True)
class Batch:
    """one unwind-ready slice of rows with the cypher that loads it."""

    name: str
    cypher: str
    rows: list[Row]


@dataclass(frozen=True)
class Tenant:
    """all node and edge rows of one generated tenant, grouped by label or edge kind."""

    seed: int
    nodes: dict[str, list[Row]]
    edges: dict[str, list[Row]]

    def node_count(self) -> int:
        """total number of node rows."""
        return sum(len(rows) for rows in self.nodes.values())

    def edge_count(self) -> int:
        """total number of relationship rows."""
        return sum(len(rows) for rows in self.edges.values())

    def batches(self, size: int = 1000) -> Iterator[Batch]:
        """yield node batches then edge batches, each at most size rows, in a fixed order."""
        for groups, cypher in ((self.nodes, NODE_CYPHER), (self.edges, EDGE_CYPHER)):
            for name, statement in cypher.items():
                rows = groups.get(name, [])
                for start in range(0, len(rows), size):
                    yield Batch(name, statement, rows[start : start + size])


def _digest(*parts: str) -> str:
    """short stable content hash."""
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _handle(rng: random.Random, first: str, last: str, taken: set[str]) -> str:
    """a slack or github style handle that is not taken yet."""
    style = rng.random()
    base = (
        f"{first}.{last}"
        if style < 0.5
        else f"{first[0]}{last}"
        if style < 0.8
        else f"{first}-{last}"
    )
    handle, n = base, 1
    while handle in taken:
        n += 1
        handle = f"{base}{n}"
    taken.add(handle)
    return handle


def _services(rng: random.Random, count: int) -> list[str]:
    """service names built from domain and kind, shuffled."""
    names = [f"{d}-{k}" for d in DOMAINS for k in SERVICE_KINDS]
    rng.shuffle(names)
    return names[: max(1, min(count, len(names)))]


class _Zipf:
    """weighted index sampler with weight 1 / rank ** exponent."""

    def __init__(self, size: int) -> None:
        self.cumulative = list(accumulate(1 / (rank + 1) ** ZIPF_EXPONENT for rank in range(size)))

    def draw(self, rng: random.Random) -> int:
        """one index, low indexes far more likely."""
        return min(
            bisect(self.cumulative, rng.random() * self.cumulative[-1]), len(self.cumulative) - 1
        )


def _actors(
    rng: random.Random, persons: int, agents: int
) -> tuple[list[Row], list[Row], list[Row]]:
    """person rows, agent rows and the reporting edges between them."""
    taken: set[str] = set()
    person_rows: list[Row] = []
    for i in range(persons):
        joined = START_MS - rng.randrange(30, 900) * DAY_MS
        left = (
            START_MS + rng.randrange(30, WINDOW_DAYS) * DAY_MS
            if rng.random() < 0.03 and i
            else None
        )
        handle = _handle(rng, rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES), taken)
        person_rows.append(
            {"id": f"actor-p{i:04d}", "handle": handle, "active_from": joined, "active_to": left}
        )
    agent_rows: list[Row] = []
    for i in range(agents):
        base = AGENT_HANDLES[i % len(AGENT_HANDLES)]
        handle = base if i < len(AGENT_HANDLES) else f"{base}-{i // len(AGENT_HANDLES) + 1}"
        agent_rows.append(
            {
                "id": f"actor-a{i:04d}",
                "handle": handle,
                "active_from": START_MS - 60 * DAY_MS,
                "active_to": None,
            }
        )
    reports: list[Row] = []
    for i in range(1, persons):
        boss = int(i * rng.random() ** 2)
        reports.append(
            {
                "src": person_rows[i]["id"],
                "dst": person_rows[boss]["id"],
                "since": person_rows[i]["active_from"],
                "until": None,
            }
        )
    for agent in agent_rows:
        boss = rng.randrange(persons)
        reports.append(
            {
                "src": agent["id"],
                "dst": person_rows[boss]["id"],
                "since": agent["active_from"],
                "until": None,
            }
        )
    return person_rows, agent_rows, reports


def _fact_texts(
    rng: random.Random, services: list[str], handles: list[str], count: int
) -> list[tuple[str, str, str, str]]:
    """unique (subject, predicate, object, text) tuples about services and teams."""
    seen: set[str] = set()
    out: list[tuple[str, str, str, str]] = []
    predicates = tuple(FACT_KINDS)
    while len(out) < count:
        service = rng.choice(services)
        predicate = predicates[rng.randrange(len(predicates))]
        major = rng.randint(1, 6)
        if predicate == "owned_by":
            team = rng.choice(TEAMS)
            subject, obj, text = (
                f"{service} v{major}",
                team,
                f"{service} v{major} is owned by {team}",
            )
        elif predicate == "reads_from":
            store = rng.choice(DATASTORES)
            subject, obj, text = service, store, f"{service} reads from {store}"
        elif predicate == "oncall":
            team, handle = rng.choice(TEAMS), rng.choice(handles)
            week = rng.randint(1, 52)
            subject, obj, text = team, handle, f"{team} on-call for week {week} is {handle}"
        elif predicate == "deprecated_on":
            day = START_MS + rng.randrange(-60, 300) * DAY_MS
            date = _iso_date(day)
            subject, obj, text = (
                f"{service} v{major}",
                date,
                f"{service} v{major} is deprecated and sunsets on {date}",
            )
        elif predicate == "latency_slo":
            ms = rng.choice((50, 100, 150, 200, 250, 300, 500, 800, 1200))
            subject, obj, text = (
                service,
                f"{ms} ms",
                f"{service} p99 latency target is {ms} ms in {rng.choice(REGIONS)}",
            )
        elif predicate == "runs_on":
            runtime = rng.choice(RUNTIMES)
            subject, obj, text = (
                service,
                runtime,
                f"{service} runs on {runtime} in {rng.choice(REGIONS)}",
            )
        else:
            limit = rng.choice((60, 120, 300, 600, 1200, 3000, 6000, 12000))
            subject, obj, text = (
                service,
                str(limit),
                f"{service} v{major} rate limit is {limit} requests per minute per tenant",
            )
        if text in seen:
            continue
        seen.add(text)
        out.append((subject, predicate, obj, text))
    return out


def _iso_date(ms: int) -> str:
    """utc calendar date of an epoch millisecond value."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def _facts(rng: random.Random, services: list[str], handles: list[str], count: int) -> list[Row]:
    """base facts, a few of them already dead."""
    rows: list[Row] = []
    dead_ids = set(rng.sample(range(count), max(1, count * 3 // 100)))
    end = START_MS + WINDOW_DAYS * DAY_MS
    for i, (subject, predicate, obj, text) in enumerate(_fact_texts(rng, services, handles, count)):
        kind = FACT_KINDS[predicate]
        learned = START_MS + rng.randrange(0, 90 * DAY_MS)
        valid_from = learned - rng.randrange(0, 3 * DAY_MS)
        confirmed = min(end, learned + rng.randrange(0, 60 * DAY_MS))
        valid_to = died = None
        status = "true"
        if i in dead_ids:
            valid_to = min(end - DAY_MS, learned + rng.randrange(DAY_MS, 60 * DAY_MS))
            died = valid_to + rng.randrange(0, 2 * DAY_MS)
            status = "dead"
        rows.append(
            {
                "id": f"fact-{i:05d}",
                "s": subject,
                "p": predicate,
                "o": obj,
                "text": text,
                "kind": kind,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "learned_at": learned,
                "died_learned_at": died,
                "status": status,
                "durability": DURABILITY[kind],
                "last_confirmed": confirmed,
                "hash": _digest(subject, predicate, obj),
            }
        )
    return rows


def _item_content(rng: random.Random, label: str, service: str, n: int) -> tuple[str, str]:
    """title and uri for one item of the given label."""
    team = rng.randrange(len(TEAMS))
    if label == "Doc":
        return (
            f"runbook: {service} {rng.choice(TOPICS)}",
            f"https://acme.atlassian.net/wiki/spaces/ENG/pages/{rng.randrange(100000, 999999)}",
        )
    if label == "Ticket":
        key, number = TEAM_KEYS[team], rng.randrange(100, 4000)
        return (
            f"{key}-{number}: {rng.choice(ACTIONS)} {service}",
            f"https://acme.atlassian.net/browse/{key}-{number}",
        )
    if label == "PR":
        number = rng.randrange(100, 9000)
        return (
            f"#{number} {rng.choice(ACTIONS)} {service}",
            f"https://github.com/acme/{service}/pull/{number}",
        )
    if label == "Commit":
        return (
            f"{rng.choice(ACTIONS)} {service}",
            f"https://github.com/acme/{service}/commit/{rng.getrandbits(160):040x}",
        )
    if label == "Answer":
        return f"who owns {service}?", f"entrelis://answer/{n:06d}"
    if label == "Step":
        return (
            f"step {rng.randint(1, 8)}: check {service} health in {rng.choice(REGIONS)}",
            f"entrelis://step/{n:06d}",
        )
    if label == "Memory":
        return f"remember: {service} is handled by {TEAMS[team]}", f"claude-code://memory/{n:06d}"
    channel = f"C{rng.getrandbits(40):010X}"[:11]
    return (
        f"is {service} still on {rng.choice(DATASTORES)}?",
        f"https://acme.slack.com/archives/{channel}/p{rng.randrange(10**15, 10**16)}",
    )


@dataclass
class _Build:
    nodes: dict[str, list[Row]]
    edges: dict[str, list[Row]]
    structural: int


def _depth_counts(derived: int) -> list[int]:
    """how many derived items sit at each hop depth, every depth present."""
    counts = [max(1, round(w * derived)) for w in DEPTH_WEIGHTS]
    counts[0] = max(1, counts[0] + derived - sum(counts))
    return counts


def _build(seed: int, item_count: int) -> _Build:
    """everything except read edges, for the given number of items."""
    rng = random.Random(seed)
    persons = max(8, item_count // 60)
    agents = max(2, persons // 10)
    fact_count = max(30, round(item_count * 0.3))
    person_rows, agent_rows, reports = _actors(rng, persons, agents)
    services = _services(rng, max(12, fact_count // 5))
    handles = [str(p["handle"]) for p in person_rows]
    facts = _facts(rng, services, handles, fact_count)
    fact_time = [int(f["learned_at"] or 0) for f in facts]
    zipf = _Zipf(fact_count)
    hub_order = list(range(fact_count))
    rng.shuffle(hub_order)

    derived = round(item_count * 0.95)
    plan = [depth for depth, n in enumerate(_depth_counts(derived), start=1) for _ in range(n)]
    plan += [0] * (item_count - len(plan))
    labels = [rng.choice(ITEM_LABELS) for _ in plan]
    nodes: dict[str, list[Row]] = {label: [] for label in NODE_CYPHER}
    edges: dict[str, list[Row]] = {name: [] for name in EDGE_CYPHER}
    nodes["Person"], nodes["Agent"], nodes["Fact"] = person_rows, agent_rows, facts
    edges["REPORTS_TO"] = reports

    active = [p for p in person_rows if p["active_to"] is None]
    pools: dict[int, list[tuple[str, int]]] = {}
    end = START_MS + WINDOW_DAYS * DAY_MS
    link_n = 0
    for n, (depth, label) in enumerate(zip(plan, labels, strict=True)):
        item_id = f"item-{n:06d}"
        title, uri = _item_content(rng, label, rng.choice(services), n)
        created = START_MS + rng.randrange(10 * DAY_MS, end - START_MS - 30 * DAY_MS)
        link_specs: list[tuple[str, list[tuple[str, str, int]]]] = []
        for _ in range(1 + (rng.random() < 0.11) + (rng.random() < 0.02) if depth else 0):
            premises: list[tuple[str, str, int]] = []
            used: set[str] = set()
            want = rng.choices((1, 2, 3), weights=(4, 4, 2))[0]
            while len(premises) < want:
                if not premises and depth > 1:
                    pid, pt = rng.choice(pools[depth - 1])
                    kind = "Item"
                elif premises and depth > 1 and rng.random() < 0.2:
                    pid, pt = rng.choice(pools[rng.randrange(1, depth)])
                    kind = "Item"
                else:
                    index = hub_order[zipf.draw(rng)]
                    pid, pt, kind = str(facts[index]["id"]), fact_time[index], "Fact"
                if pid in used:
                    continue
                used.add(pid)
                premises.append((kind, pid, pt))
            link_specs.append((rng.choices(("hard", "soft"), weights=(8, 2))[0], premises))
            created = max(
                created, max(pt for _, _, pt in premises) + rng.randrange(3_600_000, 3 * DAY_MS)
            )
        created = min(created, end)
        depends: dict[str, tuple[str, str]] = {}
        for kind, premises in link_specs:
            link_n += 1
            link_id = f"link-{link_n:06d}"
            nodes["Link"].append(
                {"id": link_id, "rule": rng.choice(LINK_RULES), "kind": kind, "created_at": created}
            )
            edges["SUPPORTS"].append({"src": link_id, "dst": item_id})
            for target_kind, pid, _ in premises:
                edges[f"PREMISE:{target_kind}"].append({"src": link_id, "dst": pid})
                if depends.get(pid, ("", "soft"))[1] == "soft":
                    depends[pid] = (target_kind, kind)
        for pid, (target_kind, kind) in depends.items():
            edges[f"DEPENDS_ON:{target_kind}"].append(
                {"src": item_id, "dst": pid, "at": created, "kind": kind}
            )
        nodes[label].append(
            {
                "id": item_id,
                "uri": uri,
                "title": title,
                "created_at": created,
                "status": "true",
                "hash": _digest(title, uri),
            }
        )
        if depth:
            pools.setdefault(depth, []).append((item_id, created))
        owner = _owner(rng, label, active, agent_rows)
        edges["OWNED_BY:Item"].append(
            {"src": item_id, "dst": owner["id"], "since": created, "until": None}
        )

    for fact in facts:
        owner = rng.choice(active)
        edges["OWNED_BY:Fact"].append(
            {"src": fact["id"], "dst": owner["id"], "since": fact["learned_at"], "until": None}
        )
    structural = sum(len(rows) for rows in edges.values())
    return _Build(nodes, edges, structural)


def _owner(rng: random.Random, label: str, persons: list[Row], agents: list[Row]) -> Row:
    """an active person, or an agent for machine-made item kinds."""
    if label in ("Answer", "Step", "Memory") and rng.random() < 0.6:
        return rng.choice(agents)
    return rng.choice(persons)


def _add_reads(seed: int, build: _Build, total: int) -> None:
    """top up read edges until the tenant has exactly total relationships."""
    rng = random.Random(seed + 1)
    items = [row for label in ITEM_LABELS for row in build.nodes[label]]
    facts = build.nodes["Fact"]
    zipf = _Zipf(len(facts))
    end = START_MS + WINDOW_DAYS * DAY_MS
    sessions = [f"sess-{rng.getrandbits(48):012x}" for _ in range(max(10, len(items) // 8))]
    while build.structural < total:
        reader = rng.choice(items)
        if rng.random() < 0.65:
            target, group = facts[zipf.draw(rng)], "READ:Fact"
            born = int(target["learned_at"])
        else:
            target, group = rng.choice(items), "READ:Item"
            if target["id"] == reader["id"]:
                continue
            born = int(target["created_at"])
        start = max(int(reader["created_at"]), born)
        at = min(end, start + rng.randrange(0, 30 * DAY_MS))
        build.edges[group].append(
            {"src": reader["id"], "dst": target["id"], "at": at, "session": rng.choice(sessions)}
        )
        build.structural += 1


def generate(seed: int, edges: int) -> Tenant:
    """build one tenant whose relationship count lands on the edges target."""
    items = max(20, round(edges / EDGES_PER_ITEM))
    low, high = STRUCTURE_SHARE
    for _ in range(12):
        build = _build(seed, items)
        if low * edges <= build.structural <= high * edges:
            break
        items = max(20, int(items * (low + high) / 2 * edges / build.structural))
    else:
        raise RuntimeError(f"could not size a tenant for {edges} edges")
    _add_reads(seed, build, edges)
    return Tenant(seed, build.nodes, build.edges)


async def load(graph: "AsyncGraph", tenant: Tenant) -> None:
    """create id indexes, wait until they are usable, then run every batch."""
    for statement in INDEX_CYPHER:
        await graph.query(statement)
    for _ in range(200):
        result = await graph.query(INDEX_LIST_CYPHER)
        if all(row[0] == "OPERATIONAL" for row in result.result_set):
            break
        await asyncio.sleep(0.02)
    else:
        raise RuntimeError("id indexes did not become operational within 4 s")
    for batch in tenant.batches():
        await graph.query(batch.cypher, {"rows": batch.rows})
