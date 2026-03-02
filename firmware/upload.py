#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
"""Upload a flat binary to the RISCY-V02 demo board and enter terminal mode.

Usage: python upload.py /dev/ttyACM0 hello.bin [--reset]

Requires: pip install pyserial
"""
import argparse
import struct
import sys
import termios
import tty

import serial


def wait_for(ser, prompt):
    """Read lines until one contains `prompt`. Print everything received."""
    while True:
        line = ser.readline()
        if not line:
            continue
        text = line.decode(errors='replace')
        sys.stdout.write(text)
        sys.stdout.flush()
        if prompt in text:
            return


def upload(ser, data, addr=0):
    """Send an L command to load `data` at `addr`."""
    header = struct.pack('<cHH', b'L', addr, len(data))
    ser.write(header + data)
    wait_for(ser, 'OK')


def terminal(ser):
    """Transparent terminal: stdin -> serial, serial -> stdout.

    Ctrl-C exits. Ctrl-R sends reset (0x12) to firmware.
    """
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin)
        ser.timeout = 0.02
        while True:
            # serial -> stdout
            rx = ser.read(256)
            if rx:
                sys.stdout.buffer.write(rx)
                sys.stdout.buffer.flush()
            # stdin -> serial
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.buffer.read(1)
                if not ch or ch == b'\x03':  # Ctrl-C
                    break
                ser.write(ch)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        print()  # newline after raw mode


def main():
    parser = argparse.ArgumentParser(
        description='Upload a binary to the RISCY-V02 demo board.')
    parser.add_argument('port', help='Serial port (e.g. /dev/ttyACM0)')
    parser.add_argument('binary', help='Flat binary file to upload')
    parser.add_argument('--reset', action='store_true',
                        help='Send Ctrl-R reset before uploading')
    parser.add_argument('--baud', type=int, default=115200,
                        help='Baud rate (default: 115200)')
    args = parser.parse_args()

    with open(args.binary, 'rb') as f:
        data = f.read()

    print(f"Uploading {len(data)} bytes from {args.binary}")

    ser = serial.Serial(args.port, args.baud, timeout=2)

    if args.reset:
        print("Sending reset...")
        ser.write(b'\x12')  # Ctrl-R

    wait_for(ser, 'Ready')

    upload(ser, data, addr=0)

    # Start execution
    ser.write(b'G')
    wait_for(ser, 'Running')

    print("--- Terminal mode (Ctrl-C to exit, Ctrl-R to reset) ---")
    terminal(ser)

    ser.close()


if __name__ == '__main__':
    main()
