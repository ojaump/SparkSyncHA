# SparkSync for Home Assistant

Custom integration for SparkSync hardware. Everything arrives over MQTT — the
integration opens its own broker connection, so Home Assistant's MQTT
integration is not required and does not need to point at the same broker.

Two kinds of device, one per config entry:

- **Generator gateways** — engine telemetry and power production, one JSON
  section per topic under `devices/<id>/`, 1 Hz.
- **3-phase meters** — a whole reading every 5 s on `SparkSync/Meter/<mac>`.
  See [MQTT.md](MQTT.md) for the payload contract.

## Install

1. HACS → Integrations → Custom repositories → add this repo (type: Integration).
2. Install **SparkSync**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → SparkSync.
4. Pick what is publishing, then enter the broker. WebSocket + TLS are on by
   default (port 443, path `/mqtt`); turn WebSocket off to reach a broker
   directly by IP or hostname over TCP — e.g. the Mosquitto add-on at
   `core-mosquitto:1883` with TLS off.

Devices are discovered from the topics they publish on; there is nothing
per-device to enter. Add the integration twice to run both kinds, or more than
once to read two brokers.

## Gateway sensors

Per generator (canonical fields, DSE and EasyGen):

- **Power**: generator power, frequency, voltage, current, power factor, load %, mains power
- **Engine**: speed, oil pressure/temperature/level, coolant temperature/level, battery voltage, fuel rate
- **Accumulated**: generated energy (kWh — usable in the Energy dashboard), engine run time, engine starts
- **Status**: control mode

Raw per-controller payloads are mapped onto those canonical names in
`normalize.py`; a new controller variant needs its entries added there.

## Meter sensors

Per node: phase and line voltages, per-phase current, active/reactive/apparent
power and power factor per phase and total, frequency. 26 sensors.

The meter's own `*_meter` totals are not exposed — they read about a third of
reality. Values are signed: active/reactive power and power factor go negative
when the site exports.

## Staleness

A device publishes only when it has a real reading, so silence is a fault, not
a plateau. Sensors go unavailable after 15 s for a meter (three cadences) and
30 s for a gateway, even while the retained status topic still says `online`.
Gateway frames are timed by their own `ts`, so a reconnect that replays a dead
gateway's last words does not read as live.
