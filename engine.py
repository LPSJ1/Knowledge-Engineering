"""Inference engine for the autonomous trailer agent (Victor's section).

Facts   : tuples in a set, e.g. ("edge", "A", "B", 40), ("blocked", "A", "B")
Rules   : list of Rule objects; each has a plain IF/THEN text and a function
          that looks at the fact set and returns the facts it concludes.
Chaining: forward chaining, repeated until no rule adds a new fact.
Link to search: stage 1 derives avoid/penalty facts -> filtered graph ->
          search -> stage 2 derives fuel facts from the found route.
"""
import heapq
from dataclasses import dataclass
from typing import Callable


@dataclass
class Rule:
    name: str
    text: str                      # plain IF/THEN, shown in the write-up
    fn: Callable[[set], set]       # facts -> set of concluded facts


def _undirected(a, b):
    return {(a, b), (b, a)}


# ---------------------------------------------------------------- rules ----
def r1(f):  # closed road
    return {("avoid", x, y) for k in f if k[0] == "closed" for x, y in _undirected(k[1], k[2])}

def r2(f):  # flooding
    return {("avoid", x, y) for k in f if k[0] == "condition" and k[3] == "flooded"
            for x, y in _undirected(k[1], k[2])}

def r3(f):  # accident
    return {("avoid", x, y) for k in f if k[0] == "accident" for x, y in _undirected(k[1], k[2])}

def r4(f):  # trailer too tall
    h = next((k[1] for k in f if k[0] == "trailer_height"), None)
    if h is None:
        return set()
    return {("avoid", x, y) for k in f if k[0] == "max_height" and k[3] < h
            for x, y in _undirected(k[1], k[2])}

def r5(f):  # heavy traffic
    return {("penalty", x, y, 1.5) for k in f if k[0] == "traffic" and k[3] == "heavy"
            for x, y in _undirected(k[1], k[2])}

def r6(f):  # roadworks
    return {("penalty", x, y, 1.3) for k in f if k[0] == "condition" and k[3] == "roadworks"
            for x, y in _undirected(k[1], k[2])}

def r7(f):  # no path found by search
    return {("no_valid_route", "no path on the filtered graph")} if ("search_failed",) in f else set()

def r8(f):  # route longer than range
    rng = next((k[1] for k in f if k[0] == "fuel_range"), None)
    km = next((k[1] for k in f if k[0] == "route_km"), None)
    return {("needs_refuel",)} if rng is not None and km is not None and km > rng else set()

def _cum(f):
    return {k[1]: k[2] for k in f if k[0] == "on_route"}

def r9(f):  # refuel station on route that splits the trip into two reachable legs
    if ("needs_refuel",) not in f:
        return set()
    rng = next(k[1] for k in f if k[0] == "fuel_range")
    total = next(k[1] for k in f if k[0] == "route_km")
    cum = _cum(f)
    ok = [(c, n) for n, c in cum.items() if ("fuel_station", n) in f and c <= rng and total - c <= rng]
    return {("refuel_at", min(ok)[1])} if ok else set()

def r10(f):  # needs fuel but no usable station
    if ("needs_refuel",) in f and not any(k[0] == "refuel_at" for k in f):
        return {("no_valid_route", "route exceeds fuel range and no reachable fuel stop")}
    return set()

RULES = [
    Rule("R1", "IF road is closed THEN avoid it", r1),
    Rule("R2", "IF road is flooded THEN avoid it", r2),
    Rule("R3", "IF road has an accident THEN avoid it", r3),
    Rule("R4", "IF road max height < trailer height THEN avoid it", r4),
    Rule("R5", "IF traffic is heavy THEN penalise the road (x1.5)", r5),
    Rule("R6", "IF road has roadworks THEN penalise the road (x1.3)", r6),
    Rule("R7", "IF search found no path THEN no valid route", r7),
    Rule("R8", "IF route km > fuel range THEN trailer needs a refuel", r8),
    Rule("R9", "IF refuel needed AND a station on the route leaves both legs within range THEN refuel there", r9),
    Rule("R10", "IF refuel needed AND no such station THEN no valid route", r10),
]


# ------------------------------------------------------- forward chaining ----
def forward_chain(facts, rules=RULES, trace=None):
    """Fire rules until nothing new is derived. Returns the extended fact set."""
    facts = set(facts)
    trace = trace if trace is not None else []
    changed = True
    while changed:
        changed = False
        for rule in rules:
            new = rule.fn(facts) - facts
            if new:
                facts |= new
                changed = True
                trace.append(f"{rule.name}: {rule.text}  ->  {sorted(map(str, new))}")
    return facts


# ----------------------------------------------------------------- search ----
def shortest_path(facts, start, dest):
    """Dijkstra over the graph with avoided edges removed and penalties applied.
    Stand-in for the Practical/Exercise 3 search; swap in the real one at integration."""
    avoid = {(k[1], k[2]) for k in facts if k[0] == "avoid"}
    pen = {(k[1], k[2]): k[3] for k in facts if k[0] == "penalty"}
    adj = {}
    for k in facts:
        if k[0] == "edge":
            _, a, b, km = k
            for x, y in _undirected(a, b):
                if (x, y) not in avoid:
                    adj.setdefault(x, []).append((y, km))
    pq, best = [(0.0, start, [start])], {}
    while pq:
        cost, node, path = heapq.heappop(pq)
        if node == dest:
            return path
        if best.get(node, float("inf")) <= cost:
            continue
        best[node] = cost
        for nxt, km in adj.get(node, []):
            heapq.heappush(pq, (cost + km * pen.get((node, nxt), 1.0), nxt, path + [nxt]))
    return None


def path_km(facts, path):
    d = {}
    for k in facts:
        if k[0] == "edge":
            d[(k[1], k[2])] = d[(k[2], k[1])] = k[3]
    legs = [d[(a, b)] for a, b in zip(path, path[1:])]
    return legs


# ------------------------------------------------------------ plan_route ----
def plan_route(facts, start, dest):
    """Returns dict: route (list|None), distance_km, refuel_at, reasons (list[str])."""
    trace = []
    f = forward_chain(set(facts) | {("start", start), ("dest", dest)}, trace=trace)   # stage 1
    path = shortest_path(f, start, dest)
    if path is None:
        f = forward_chain(f | {("search_failed",)}, trace=trace)
        return {"route": None, "distance_km": None, "refuel_at": None, "reasons": trace}

    legs = path_km(f, path)
    cum, run = [0], 0
    for l in legs:
        run += l
        cum.append(run)
    f |= {("route_km", run)} | {("on_route", n, c) for n, c in zip(path, cum)}
    trace.append(f"SEARCH: route {' -> '.join(path)}, {run} km")
    f = forward_chain(f, trace=trace)                                                 # stage 2

    bad = next((k for k in f if k[0] == "no_valid_route"), None)
    if bad:
        return {"route": None, "distance_km": None, "refuel_at": None, "reasons": trace}
    stop = next((k[1] for k in f if k[0] == "refuel_at"), None)
    return {"route": path, "distance_km": run, "refuel_at": stop, "reasons": trace}
