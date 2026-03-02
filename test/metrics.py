#!/usr/bin/env python3
"""Print key post-harden metrics: area, utilization, fmax per corner."""

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

metrics_path = PROJECT_DIR / "runs/wokwi/final/metrics.json"
resolved_path = PROJECT_DIR / "runs/wokwi/resolved.json"

m = json.load(open(metrics_path))
cp = json.load(open(resolved_path)).get("CLOCK_PERIOD", 20)

area = m.get("design__instance__area", 0)
core = m.get("design__core__area", 0)
util = m.get("design__instance__utilization", 0)

print(f"Clock period: {cp} ns")
print(f"Instance area: {area:.1f} um²")
print(f"Core area:     {core:.1f} um²")
print(f"Utilization:   {util*100:.1f}%")
print()

corners = sorted(set(
    k.split("corner:")[1] for k in m if "setup__wns__corner:" in k
))

print(f"{'Corner':<35s} {'Setup WNS':>10s} {'Fmax (MHz)':>11s}")
print("─" * 58)
for c in corners:
    wns = m.get(f"timing__setup__wns__corner:{c}", 0)
    fmax = 1000.0 / (cp - wns) if cp - wns > 0 else float("inf")
    flag = " !!!" if wns < 0 else ""
    print(f"{c:<35s} {wns:>10.3f} {fmax:>11.1f}{flag}")
print()
