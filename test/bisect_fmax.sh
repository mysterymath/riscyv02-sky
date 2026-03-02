#!/usr/bin/env bash
# Binary search for all-corners-clean clock period.
# Usage: ./bisect_fmax.sh <clock_period_ns>
# Runs one harden iteration, prints worst setup WNS across all corners.

set -euo pipefail

PERIOD="${1:?Usage: $0 <clock_period_ns>}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$PROJECT_DIR/src/config.json"
METRICS="$PROJECT_DIR/runs/wokwi/final/metrics.json"
TT_VENV="${TT_VENV:-$HOME/ttsetup/venv}"

echo "=== Hardening at CLOCK_PERIOD=$PERIOD ns ==="

# Update CLOCK_PERIOD in config.json
sed -i "s/\"CLOCK_PERIOD\": [0-9.]*/\"CLOCK_PERIOD\": $PERIOD/" "$CONFIG"

# Clean previous run
rm -rf "$PROJECT_DIR/runs/wokwi"

# Run harden
cd "$PROJECT_DIR"
. "$TT_VENV/bin/activate"
python ./tt/tt_tool.py --create-user-config
python ./tt/tt_tool.py --harden

# Extract worst WNS across all corners
python3 -c "
import json, sys
m = json.load(open('$METRICS'))
corners = [k for k in m if 'setup__wns__corner:' in k]
if not corners:
    print('ERROR: no timing corners found')
    sys.exit(1)
worst_wns = min(m[k] for k in corners)
worst_corner = min(corners, key=lambda k: m[k])
print()
print(f'CLOCK_PERIOD = $PERIOD ns')
print(f'Worst WNS    = {worst_wns:.3f} ns')
print(f'Corner       = {worst_corner.split(\"corner:\")[1]}')
if worst_wns < 0:
    print(f'RESULT: FAIL (need ~{float(\"$PERIOD\") - worst_wns:.1f} ns)')
else:
    print(f'RESULT: PASS')
"
