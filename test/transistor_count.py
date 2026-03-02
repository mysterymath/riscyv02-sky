#!/usr/bin/env python3
"""Estimate transistor count from SKY130 sky130_fd_sc_hd synthesis results.

Parses the PDK's CDL SPICE netlist to count MOSFETs per standard cell,
then multiplies by instance counts from the Yosys synthesis report.
"""

import json
import re
import sys
from pathlib import Path

# Locate project root (directory containing runs/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# Default paths — override via environment or arguments
CDL_SEARCH_PATTERNS = [
    Path.home() / "ttsetup/pdk/sky130A/libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl",
    Path.home() / "ttsetup/pdk/ciel/sky130/versions/*/sky130A/libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl",
]

def find_cdl():
    """Find the sky130_fd_sc_hd standard cell CDL file."""
    import os, glob
    pdk_root = os.environ.get("PDK_ROOT", "")
    if pdk_root:
        primary = f"{pdk_root}/sky130A/libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl"
        if Path(primary).exists():
            return Path(primary)
    for pattern in CDL_SEARCH_PATTERNS:
        import glob as g
        matches = g.glob(str(pattern))
        if matches:
            return Path(matches[0])
    print("ERROR: Cannot find sky130_fd_sc_hd.cdl. Set PDK_ROOT.", file=sys.stderr)
    sys.exit(1)

def find_stat_json():
    """Find the Yosys synthesis stat.json."""
    candidates = sorted(PROJECT_DIR.glob("runs/*/06-yosys-synthesis/reports/stat.json"))
    if not candidates:
        print(f"ERROR: No stat.json found under {PROJECT_DIR}/runs/", file=sys.stderr)
        sys.exit(1)
    return candidates[-1]  # most recent run

def parse_cdl(cdl_path):
    """Parse CDL file, return {cell_name: mosfet_count}."""
    cell_counts = {}
    current_cell = None
    count = 0
    with open(cdl_path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith(".SUBCKT "):
                current_cell = stripped.split()[1]
                count = 0
            elif stripped.startswith(".ENDS"):
                if current_cell:
                    cell_counts[current_cell] = count
                current_cell = None
            elif current_cell and re.match(r"^M", stripped):
                count += 1
    return cell_counts

def main():
    cdl_path = find_cdl()
    stat_path = find_stat_json()

    cdl_counts = parse_cdl(cdl_path)

    with open(stat_path) as f:
        stat = json.load(f)

    # Use top module's cell counts (prefer tt_um_* over sub-modules)
    modules = stat["modules"]
    top_modules = [m for m in modules if "tt_um_" in m]
    module_name = top_modules[0] if top_modules else next(iter(modules))
    display_name = module_name.lstrip("\\")
    cells_by_type = dict(modules[module_name]["num_cells_by_type"])

    # Flatten sub-module references: replace sub-module entries with their cells
    changed = True
    while changed:
        changed = False
        for cell in list(cells_by_type):
            sub_key = f"\\{cell}"
            if cell not in cdl_counts and sub_key in modules:
                count = cells_by_type.pop(cell)
                for sub_cell, sub_count in modules[sub_key]["num_cells_by_type"].items():
                    cells_by_type[sub_cell] = cells_by_type.get(sub_cell, 0) + count * sub_count
                changed = True

    # Validate all cells exist in CDL
    missing = [c for c in cells_by_type if c not in cdl_counts]
    if missing:
        print(f"ERROR: Cells not found in CDL: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # Build table rows: (cell, instances, tx_per_cell, total_tx)
    rows = []
    for cell, instances in cells_by_type.items():
        tx = cdl_counts[cell]
        rows.append((cell, instances, tx, instances * tx))
    rows.sort(key=lambda r: -r[3])

    total_instances = sum(r[1] for r in rows)
    total_tx = sum(r[3] for r in rows)

    # Print report
    print(f"Transistor Count Estimate — {display_name}")
    print("PDK: SKY130 sky130_fd_sc_hd")
    print("Source: CDL SPICE netlists + Yosys synthesis report")
    print()
    fmt = "{:<30s} {:>9s} {:>8s} {:>12s}"
    print(fmt.format("Cell Type", "Instances", "Tx/Cell", "Transistors"))
    print("─" * 62)
    for cell, inst, tx_per, total in rows:
        print(f"{cell:<30s} {inst:>9,d} {tx_per:>8d} {total:>12,d}")
    print("─" * 62)
    print(f"{'TOTAL (' + str(len(rows)) + ' cell types)':<30s} {total_instances:>9,d} {'—':>8s} {total_tx:>12,d}")
    print()
    print("Sources:")
    print(f"  CDL: {cdl_path}")
    print(f"  Synthesis: {stat_path}")
    print()
    print("Assumptions:")
    print("  1. One M-line in CDL = one MOSFET = one transistor")
    print("  2. Post-synthesis counts (excludes PnR fill/buffer/CTS cells)")
    print("  3. ng (multi-finger) is layout, not additional devices")

if __name__ == "__main__":
    main()
