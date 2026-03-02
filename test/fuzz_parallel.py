#!/usr/bin/env python3
"""Parallel fuzz runner for RISCY-V02.

Launches multiple cocotb fuzz workers with non-overlapping seeds,
separate build dirs, and no VCD dumping.

Usage:
    python fuzz_parallel.py -j 16              # 16 workers, RTL
    python fuzz_parallel.py -j 8 --gates       # 8 workers, gate-level
    python fuzz_parallel.py -j 32 --seed 5000  # custom start seed
    python fuzz_parallel.py -j 8 --iters 1000  # finite per worker
"""

import argparse
import os
import signal
import subprocess
import sys
import time

SEED_SPACING = 1_000_000


def main():
    parser = argparse.ArgumentParser(description="Parallel RISCY-V02 fuzz runner")
    parser.add_argument("-j", "--jobs", type=int, required=True, help="Number of workers")
    parser.add_argument("--seed", type=int, default=0, help="Starting seed (default: 0)")
    parser.add_argument("--iters", type=int, default=0, help="Iterations per worker (0=infinite)")
    parser.add_argument("--gates", action="store_true", help="Run gate-level simulation (requires PDK_ROOT)")
    args = parser.parse_args()

    if args.gates and not os.environ.get("PDK_ROOT"):
        print("ERROR: --gates requires PDK_ROOT to be set", file=sys.stderr)
        sys.exit(1)

    prefix = "gl_fuzz" if args.gates else "fuzz"
    procs = []
    for i in range(args.jobs):
        seed = args.seed + i * SEED_SPACING
        log = f"{prefix}_{i}.log"
        env = {
            **os.environ,
            "FUZZ_SEED": str(seed),
            "FUZZ_ITERS": str(args.iters),
        }
        cmd = [
            "make",
            f"SIM_BUILD=sim_build/{prefix}_{i}",
            "NODUMP=1",
            "COCOTB_TEST_MODULES=test_fuzz",
            f"COCOTB_RESULTS_FILE=results_{prefix}_{i}.xml",
        ]
        if args.gates:
            cmd.append("GATES=yes")
        with open(log, "w") as f:
            p = subprocess.Popen(
                cmd, env=env, stdout=f, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        procs.append((i, p, log))
        print(f"Worker {i}: seed={seed} pid={p.pid} log={log}")

    print(f"\n{args.jobs} workers running. Ctrl-C to stop all.\n")

    # Track file positions for tailing logs
    log_pos = {i: 0 for i, _, _ in procs}
    KEYWORDS = ("Progress:", "Final:", "MISMATCH", "FAIL", "ERROR")

    def tail_logs():
        for i, _, log in procs:
            try:
                with open(log, "r") as f:
                    f.seek(log_pos[i])
                    for line in f:
                        if any(kw in line for kw in KEYWORDS):
                            # Strip cocotb timestamp prefix, keep the meat
                            msg = line.strip()
                            print(f"[w{i}] {msg}")
                    log_pos[i] = f.tell()
            except FileNotFoundError:
                pass

    def kill_all():
        for _, p, _ in procs:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        while procs:
            time.sleep(1)
            tail_logs()
            still_running = []
            for i, p, log in procs:
                ret = p.poll()
                if ret is None:
                    still_running.append((i, p, log))
                elif ret != 0:
                    print(f"FAIL: Worker {i} exited with code {ret} — see {log}")
                else:
                    print(f"OK:   Worker {i} finished")
            procs = still_running
    except KeyboardInterrupt:
        print("\nCtrl-C received, killing all workers...")
        kill_all()
    finally:
        tail_logs()  # flush any remaining lines
        # Clean up results files
        for i in range(args.jobs):
            f = f"results_{prefix}_{i}.xml"
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    main()
