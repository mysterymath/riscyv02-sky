#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Standalone emulator for RISCY-V02.
#
# Emulates 64K SRAM + memory-mapped UART (matching the demo board firmware).
# Runs a flat binary to completion (STP instruction).
#
# Usage: python test/emu.py program.bin

import os
import select
import sys

from riscyv02_sim import RISCYV02Sim


class EmulatorRAM(bytearray):
    """64K RAM with memory-mapped UART at 0xFF00-0xFF02."""

    def __getitem__(self, key):
        if isinstance(key, int):
            if key == 0xFF01:  # UART RX
                if select.select([sys.stdin], [], [], 0)[0]:
                    b = os.read(sys.stdin.fileno(), 1)
                    return b[0] if b else 0
                return 0
            if key == 0xFF02:  # UART status
                has_rx = 1 if select.select([sys.stdin], [], [], 0)[0] else 0
                return 1 | (has_rx << 1)  # bit 0: TX ready, bit 1: RX available
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        if isinstance(key, int) and key == 0xFF00:  # UART TX
            os.write(sys.stdout.fileno(), bytes([value & 0xFF]))
            return
        super().__setitem__(key, value)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} program.bin", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'rb') as f:
        data = f.read()

    ram = EmulatorRAM(65536)
    ram[:len(data)] = data

    sim = RISCYV02Sim(ram)
    sim.ram = ram  # Use MMIO-aware subclass (constructor copies to plain bytearray)

    # Set terminal to raw mode for character-at-a-time I/O
    old_settings = None
    if sys.stdin.isatty():
        import termios
        import tty
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin)

    try:
        while not sim.stopped:
            sim.tick(irqb=True, nmib=True, rdy=True)
    except KeyboardInterrupt:
        pass
    finally:
        if old_settings is not None:
            import termios
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == '__main__':
    main()
