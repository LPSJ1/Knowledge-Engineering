"""Phase 4 scenarios. Expected answers were written before running."""
from engine import plan_route

# Hand-written KB (placeholder until Eric's real graph is plugged in)
BASE = {
    ("edge", "Depot", "X", 40), ("edge", "X", "Port", 40),   # 80 km
    ("edge", "Depot", "Y", 50), ("edge", "Y", "Port", 50),   # 100 km
    ("fuel_station", "X"), ("fuel_station", "Y"),
    ("fuel_range", 200),
}

def run(extra=(), remove=()):
    kb = (BASE - set(remove)) | set(extra)
    return plan_route(kb, "Depot", "Port")

def test_1_nothing_blocked():
    r = run()
    assert r["route"] == ["Depot", "X", "Port"] and r["distance_km"] == 80 and r["refuel_at"] is None

def test_2_shortest_blocked_reroute():
    r = run({("closed", "Depot", "X")})
    assert r["route"] == ["Depot", "Y", "Port"] and r["distance_km"] == 100

def test_3_low_fuel_adds_stop():
    r = run({("fuel_range", 70)}, remove={("fuel_range", 200)})
    assert r["route"] == ["Depot", "X", "Port"] and r["refuel_at"] == "X"

def test_4_blocked_and_low_fuel():
    r = run({("closed", "Depot", "X"), ("fuel_range", 70)}, remove={("fuel_range", 200)})
    assert r["route"] == ["Depot", "Y", "Port"] and r["refuel_at"] == "Y"

def test_5_everything_blocked():
    r = run({("closed", "Depot", "X"), ("accident", "Depot", "Y")})
    assert r["route"] is None

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
