#!/usr/bin/env python3
"""
HMI LAN (RJ45) Modbus TCP CSV Logger for Laptop / Raspberry Pi

Install:
    python3 -m pip install pymodbus

Architecture:
    PLC --(serial)--> HMI --(LAN / RJ45, Modbus TCP)--> Laptop / Raspberry Pi -> CSV

Notes:
    - Timestamp format matches YYYY-MM-DD HH:MM:SS:mmm (e.g., 2026-11-20 15:14:10:100).
    - Default HMI_PORT is 5020 for easy testing with HMI_TEST_SENDER.py (no admin
      rights required). Change HMI_PORT to 502 when connecting to a live HMI.
    - Automatically handles pymodbus version differences (device_id / slave / unit).
"""

import csv
import inspect
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusTcpClient

# =========================================================
# 1. NETWORK & POLLING SETTINGS
# =========================================================

HMI_IP = "192.168.1.100"  # Replace with the test system's or live HMI's IP address
HMI_PORT = 5020           # Use 5020 with HMI_TEST_SENDER.py; change to 502 for live HMI
UNIT_ID = 1               # Verify the HMI Modbus TCP Unit/Slave ID

POLL_INTERVAL_SECONDS = 1.0
RESPONSE_TIMEOUT_SECONDS = 2.0
RECONNECT_DELAY_SECONDS = 3.0

# Base zero-based Modbus holding-register offset on the HMI.
# Each channel address is computed as START_ADDRESS + offset.
START_ADDRESS = 0

# True: read all contiguous registers in a single Modbus FC03 request.
# False: read each register individually (use if the HMI rejects block reads).
READ_BLOCK = True

# False = unsigned 16-bit integers (0..65535)
# True  = signed 16-bit integers (-32768..32767)
SIGNED_16BIT = False

# CSV output settings
OUTPUT_FOLDER = Path(__file__).resolve().parent / "csv_logs"
CSV_FILE_PREFIX = "hmi_data_"
TIMESTAMP_COLUMN = "Time stamp"
FLUSH_EVERY_CYCLE = True

# =========================================================
# 2. CHANNEL MAP (SEQUENCE-WISE)
# =========================================================
# Each entry occupies one 16-bit holding register at (START_ADDRESS + offset).
# Trim or reorder to match the exact channels exposed on your HMI LAN port.

CHANNELS = [
    {"name": "MW_SPEED",   "offset": 0},
    {"name": "MW_LOP",     "offset": 1},
    {"name": "MW_CWT_OUT", "offset": 2},
    {"name": "MW_CWT_IN",  "offset": 3},
    {"name": "MW_FP",      "offset": 4},
    {"name": "MW_EXH_LB",  "offset": 5},
    {"name": "MW_EXH_RB",  "offset": 6},
    {"name": "MW_LOT",     "offset": 7},
    {"name": "MW_SWP",     "offset": 8},
    {"name": "MW_CWP",     "offset": 9},
    {"name": "MW_CA_IN",   "offset": 10},
    {"name": "MW_CA_OUT",  "offset": 11},
    {"name": "MW_DE",      "offset": 12},
    {"name": "MW_NDE",     "offset": 13},
    {"name": "MW_R1",      "offset": 14},
    {"name": "MW_R2",      "offset": 15},
    {"name": "MW_Y1",      "offset": 16},
    {"name": "MW_Y2",      "offset": 17},
    {"name": "MW_B1",      "offset": 18},
    {"name": "MW_B2",      "offset": 19},
    {"name": "MW_SAP",     "offset": 20},
    {"name": "MW_ENCL",    "offset": 21},
]


# =========================================================
# 3. TIMESTAMP & CSV HELPERS
# =========================================================

def local_now():
    return datetime.now().astimezone()


def format_timestamp(dt):
    """Format timestamp as YYYY-MM-DD HH:MM:SS:mmm (e.g. 2026-11-20 15:14:10:100)."""
    ms = dt.microsecond // 1000
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}:{ms:03d}"


def open_daily_csv(current_dt):
    """Open today's CSV file in append mode and write header if empty."""
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_FOLDER / f"{CSV_FILE_PREFIX}{current_dt.strftime('%Y%m%d')}.csv"
    has_content = path.exists() and path.stat().st_size > 0

    file_obj = path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        file_obj,
        fieldnames=[TIMESTAMP_COLUMN] + [ch["name"] for ch in CHANNELS],
        extrasaction="ignore",
    )

    if not has_content:
        writer.writeheader()
        file_obj.flush()

    print(f"CSV file: {path}")
    return file_obj, writer


# =========================================================
# 4. MODBUS TCP READ & DECODE
# =========================================================

def resolve_unit_kwarg(client):
    """Return the keyword name expected by the installed pymodbus version."""
    params = inspect.signature(client.read_holding_registers).parameters
    for candidate in ("device_id", "slave", "unit"):
        if candidate in params:
            return candidate
    return None


def read_holding_registers_compat(client, address, count, unit_kwarg):
    kwargs = {"address": address, "count": count}
    if unit_kwarg is not None:
        kwargs[unit_kwarg] = UNIT_ID
    return client.read_holding_registers(**kwargs)


def decode_register(value):
    value = int(value)
    if SIGNED_16BIT and value >= 0x8000:
        value -= 0x10000
    return value


def read_channels(client, unit_kwarg):
    """Read all configured holding registers from the HMI."""
    addresses = [START_ADDRESS + ch["offset"] for ch in CHANNELS]

    if READ_BLOCK:
        expected = list(range(addresses[0], addresses[0] + len(CHANNELS)))
        if addresses != expected:
            raise ValueError(
                "READ_BLOCK=True requires contiguous, ascending channel offsets."
            )

        response = read_holding_registers_compat(
            client,
            address=addresses[0],
            count=len(CHANNELS),
            unit_kwarg=unit_kwarg,
        )

        if response.isError():
            raise RuntimeError(f"Modbus TCP block read failed: {response}")

        if len(response.registers) != len(CHANNELS):
            raise RuntimeError(
                f"Expected {len(CHANNELS)} registers, "
                f"received {len(response.registers)}"
            )

        return {
            ch["name"]: decode_register(response.registers[idx])
            for idx, ch in enumerate(CHANNELS)
        }

    values = {}
    for ch, addr in zip(CHANNELS, addresses):
        response = read_holding_registers_compat(
            client,
            address=addr,
            count=1,
            unit_kwarg=unit_kwarg,
        )

        if response.isError():
            raise RuntimeError(
                f"Read failed for {ch['name']} at address {addr}: {response}"
            )

        if not response.registers:
            raise RuntimeError(f"No register returned for {ch['name']}")

        values[ch["name"]] = decode_register(response.registers[0])

    return values


# =========================================================
# 5. MAIN LOOP
# =========================================================

def validate_config():
    if not CHANNELS:
        raise RuntimeError("CHANNELS cannot be empty.")

    names = [ch["name"] for ch in CHANNELS]
    offsets = [ch["offset"] for ch in CHANNELS]

    if len(names) != len(set(names)):
        raise RuntimeError("Channel names must be unique.")
    if len(offsets) != len(set(offsets)):
        raise RuntimeError("Channel offsets must be unique.")


def main():
    validate_config()

    client = ModbusTcpClient(
        host=HMI_IP,
        port=HMI_PORT,
        timeout=RESPONSE_TIMEOUT_SECONDS,
    )
    unit_kwarg = resolve_unit_kwarg(client)

    csv_file = None
    writer = None
    open_date = None

    print("HMI LAN (RJ45) Modbus TCP CSV Logger")
    print(f"HMI target: {HMI_IP}:{HMI_PORT} (Unit ID: {UNIT_ID})")
    print(f"Channels: {len(CHANNELS)} (start address: {START_ADDRESS}, block read: {READ_BLOCK})")
    print(f"Poll interval: {POLL_INTERVAL_SECONDS}s | Signed 16-bit: {SIGNED_16BIT}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            try:
                if not client.connected:
                    if not client.connect():
                        raise ConnectionError(
                            f"Cannot connect to HMI at {HMI_IP}:{HMI_PORT}"
                        )
                    print(f"Connected to HMI at {HMI_IP}:{HMI_PORT}")

                now = local_now()
                today = now.date()

                if csv_file is None or today != open_date:
                    if csv_file is not None:
                        csv_file.flush()
                        csv_file.close()
                    csv_file, writer = open_daily_csv(now)
                    open_date = today

                cycle_start = time.monotonic()
                timestamp = format_timestamp(now)

                try:
                    values = read_channels(client, unit_kwarg)

                    row = {TIMESTAMP_COLUMN: timestamp}
                    row.update(values)

                    writer.writerow(row)
                    if FLUSH_EVERY_CYCLE:
                        csv_file.flush()

                    summary = " | ".join(
                        f"{name}={value}" for name, value in values.items()
                    )
                    print(f"{timestamp} | OK | {summary}")

                except Exception as exc:
                    print(f"{timestamp} | POLL ERROR: {exc}")
                    client.close()
                    time.sleep(RECONNECT_DELAY_SECONDS)

                elapsed = time.monotonic() - cycle_start
                time.sleep(max(0.0, POLL_INTERVAL_SECONDS - elapsed))

            except Exception as exc:
                print(f"Connection error: {exc}")
                client.close()
                time.sleep(RECONNECT_DELAY_SECONDS)

    except KeyboardInterrupt:
        print("\nStopping logger...")

    finally:
        client.close()
        if csv_file is not None and not csv_file.closed:
            csv_file.flush()
            csv_file.close()
        print(f"Logger stopped. CSV files saved in: {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()