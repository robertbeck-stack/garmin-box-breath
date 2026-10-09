# garmin-box-breath

Box breathing coach paced by your live heart rate, read straight from a Garmin watch's
Bluetooth LE "Broadcast Heart Rate" feature — no phone or Garmin Connect needed.

Instead of counting fixed seconds for inhale / hold / exhale / hold, each phase lasts
a fixed number of *heartbeats* (default 5), so the pacing naturally follows your current
heart rate.

## How it works

- `hr_server.py` scans for a BLE device advertising the standard Heart Rate Service
  (`0x180D`), connects, and subscribes to heart rate notifications.
- It serves a small local web app on `http://127.0.0.1:8765/`:
  - a box-breathing circle that expands/contracts over N heartbeats per phase
    (in → hold → out → hold)
  - a live chart of heart rate over the last 10 minutes
- No data leaves your machine — everything runs locally over Bluetooth + localhost HTTP.

## Setup

On the watch: **Controls → Broadcast Heart Rate** (or enable *Broadcast During Activity*
in Settings → Sensors & Accessories → Wrist Heart Rate).

```bash
pip install -r requirements.txt
python hr_server.py
```

Then open http://127.0.0.1:8765/ in a browser.

## Notes / limitations

- Garmin's BLE broadcast only sends an averaged BPM value per notification (no
  per-beat RR intervals), so beat timing is derived from the current BPM rather than
  true R-R intervals.
- Windows BLE device addresses can rotate; the scanner matches on the advertised
  Heart Rate Service UUID rather than a fixed MAC address.
- The 10-minute chart buffer is in-memory only and resets when the server restarts.

## TODO (later)

- Persist history across restarts
- Configurable breathing pattern presets (4-7-8, etc.)
- Package as a double-clickable app instead of a script
