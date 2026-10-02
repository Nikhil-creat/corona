"""Reference facility topology (seeded into the temporal graph; served to the 3D UI)."""
from __future__ import annotations

import math

NODES: list[dict] = [
    {"id": f"N-{i:02d}", "name": name, "criticality": crit, "x": round(14 * math.cos(a), 2), "z": round(14 * math.sin(a), 2) }
    for i, (name, crit, a) in enumerate(
        [
            ("Power Core", 0.95, 0.0), ("Cooling Loop A", 0.8, 0.52), ("Cooling Loop B", 0.8, 1.05),
            ("Compute Rack 1", 0.7, 1.57), ("Compute Rack 2", 0.7, 2.09), ("Turbine Hall", 0.9, 2.62),
            ("Pump Station", 0.6, 3.14), ("Gantry Crane", 0.4, 3.67), ("Conveyor Spine", 0.5, 4.19),
            ("Switchgear", 0.85, 4.71), ("Transformer", 0.9, 5.24), ("Control Room", 0.75, 5.76),
        ],
        start=1,
    )
]
# (dependent, dependency)
EDGES: list[tuple[str, str]] = [
    ("N-02", "N-01"), ("N-03", "N-01"), ("N-04", "N-02"), ("N-05", "N-03"), ("N-06", "N-01"),
    ("N-07", "N-02"), ("N-08", "N-06"), ("N-09", "N-06"), ("N-10", "N-11"), ("N-01", "N-10"),
    ("N-12", "N-10"), ("N-04", "N-12"),
]
NODE_IDS = [n["id"] for n in NODES]
