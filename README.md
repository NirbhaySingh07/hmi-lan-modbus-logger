# HMI LAN (RJ45) Modbus TCP CSV Logger

Python data logger for collecting 16-bit holding registers from an HMI over **LAN (RJ45) / Modbus TCP** on a laptop or Raspberry Pi, with automatic daily CSV rotation and millisecond timestamps (`YYYY-MM-DD HH:MM:SS:mmm`).

## Project Structure

- `LAN_RECEIVER.py` — Main Modbus TCP client that polls the HMI every second and writes daily CSV files to `csv_logs/hmi_data_YYYYMMDD.csv`.
- `HMI_TEST_SENDER.py` — Companion Modbus TCP simulator (`pymodbus 3.12+ / 3.16+` `SimDevice`/`SimData` API) for lab testing over LAN or Raspberry Pi before connecting to the live HMI.
- `requirements.txt` — Python dependencies.
- `.gitignore` — Excludes `csv_logs/` and virtual environments from Git commits.

## Installation

### Windows / Laptop
```bash
python -m pip install -r requirements.txt
```

### Raspberry Pi (Bookworm / Trixie)
```bash
python3 -m venv ~/modbus_env
source ~/modbus_env/bin/activate
pip install -r requirements.txt
```

## Lab Test (Simulator -> Receiver)

1. Start the simulator on the test PC or Raspberry Pi:
   ```bash
   python3 HMI_TEST_SENDER.py
   ```
2. In `LAN_RECEIVER.py`, set `HMI_IP` to the simulator's LAN IP (keep `HMI_PORT = 5020`).
3. Run the receiver on your laptop or Raspberry Pi:
   ```bash
   python3 LAN_RECEIVER.py
   ```
4. Press `Ctrl+C` to stop and inspect `csv_logs/hmi_data_YYYYMMDD.csv`.

## Live HMI Deployment

Update the settings at the top of `LAN_RECEIVER.py`:
- `HMI_IP` — Live HMI IPv4 address (ensure the logger's Ethernet adapter is on the same subnet).
- `HMI_PORT` — Change from `5020` to `502` (standard Modbus TCP port).
- `UNIT_ID`, `START_ADDRESS`, `SIGNED_16BIT`, and `CHANNELS` — Match your HMI's Modbus TCP register map.
