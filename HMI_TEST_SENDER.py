#!/usr/bin/env python3
"""
Modbus TCP HMI Simulator for Testing LAN_RECEIVER.py Over LAN or Wi-Fi
(Native pymodbus 3.12+ / 3.16+ SimData + SimDevice API — no deprecation warnings)

Install:
    python3 -m pip install pymodbus

Usage:
    Run this script on your second system (acting as the HMI).
    Then set HMI_IP in LAN_RECEIVER.py on your laptop to this system's IP
    address (e.g., 192.168.1.106 on the test router) and run LAN_RECEIVER.py.
"""

import random
import socket

from pymodbus.server import StartTcpServer
from pymodbus.simulator import SimData, SimDevice

try:
    from pymodbus.simulator import DataType
except ImportError:
    from pymodbus.constants import DataType

# =========================================================
# SIMULATOR SETTINGS
# =========================================================

BIND_HOST = "0.0.0.0"   # Listen on all interfaces (LAN + Wi-Fi)
PORT = 5020             # Non-privileged port (no admin/sudo needed)
NUM_CHANNELS = 22       # Matches LAN_RECEIVER.py CHANNELS count

_tick = 0


def detect_local_ips():
    """Return local IPv4 addresses on this machine for easy reference."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips) or ["127.0.0.1"]


def generate_simulated_values():
    """Generate 22 changing 16-bit unsigned values matching LAN_RECEIVER.py."""
    global _tick
    _tick += 1
    return [
        1500 + (_tick % 50),                     # MW_SPEED
        420 + random.randint(-5, 5),             # MW_LOP
        780 + random.randint(-3, 3),             # MW_CWT_OUT
        710 + random.randint(-3, 3),             # MW_CWT_IN
        350 + random.randint(-4, 4),             # MW_FP
        4100 + random.randint(-15, 15),          # MW_EXH_LB
        4080 + random.randint(-15, 15),          # MW_EXH_RB
        650 + random.randint(-2, 2),             # MW_LOT
        220 + random.randint(-3, 3),             # MW_SWP
        280 + random.randint(-3, 3),             # MW_CWP
        340 + random.randint(-2, 2),             # MW_CA_IN
        460 + random.randint(-2, 2),             # MW_CA_OUT
        520 + random.randint(-2, 2),             # MW_DE
        500 + random.randint(-2, 2),             # MW_NDE
        610 + random.randint(-3, 3),             # MW_R1
        615 + random.randint(-3, 3),             # MW_R2
        605 + random.randint(-3, 3),             # MW_Y1
        608 + random.randint(-3, 3),             # MW_Y2
        612 + random.randint(-3, 3),             # MW_B1
        614 + random.randint(-3, 3),             # MW_B2
        2650 + random.randint(-5, 5),            # MW_SAP
        390 + random.randint(-2, 2),             # MW_ENCL
    ]


async def refresh_registers_on_read(
    function_code,
    start_address,
    address,
    count,
    current_registers,
    set_values,
):
    """Update holding registers inline right before every read response."""
    if set_values is None:
        fresh = generate_simulated_values()
        limit = min(len(fresh), len(current_registers))
        current_registers[:limit] = fresh[:limit]
    return None


def main():
    initial_values = generate_simulated_values()
    device = SimDevice(
        id=0,  # Catch-all: answers any Unit ID (0, 1, etc.)
        simdata=[
            SimData(
                address=0,
                values=initial_values,
                datatype=DataType.REGISTERS,
            )
        ],
        action=refresh_registers_on_read,
    )

    print("Modbus TCP HMI Test Simulator")
    print(f"Listening on {BIND_HOST}:{PORT} ({NUM_CHANNELS} holding registers, addr 0..{NUM_CHANNELS - 1})")
    print("Set HMI_IP in LAN_RECEIVER.py on your laptop to the IP on your test router:")
    for ip in detect_local_ips():
        print(f"  -> {ip}")
    print("Press Ctrl+C to stop.")

    try:
        StartTcpServer(context=device, address=(BIND_HOST, PORT))
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


if __name__ == "__main__":
    main()