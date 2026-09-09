# SparkSync for Home Assistant

Custom integration for the SparkSync generator gateway API. Exposes engine
telemetry and power production as sensors for every device your account can
read.

## Install

1. HACS → Integrations → Custom repositories → add this repo (type: Integration).
2. Install **SparkSync**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → SparkSync.
4. Pick a source:
   - **Gateway API** - the API URL (e.g. `http://localhost:4000`), username, password.
   - **MQTT meters** - broker host and port. WebSocket + TLS are on by default
     (path `/mqtt`); turn WebSocket off to reach a broker directly by IP or
     hostname over TCP, e.g. the Mosquitto add-on at `core-mosquitto:1883` with
     TLS off. Base topic stays `SparkSync/Meter`; meter nodes are discovered
     from their topics, nothing per-device to enter.

Add the integration twice to run both.

## Sensors

Per device (canonical fields, DSE and EasyGen):

- **Power**: generator power, frequency, voltage, current, power factor, load %, mains power
- **Engine**: speed, oil pressure/temperature/level, coolant temperature/level, battery voltage, fuel rate
- **Accumulated**: generated energy (kWh — usable in the Energy dashboard), engine run time, engine starts
- **Status**: control mode

Polls `/info` every 5 s per device.

## Meter sensors (MQTT mode)

Per node, from the flat payload in [MQTT.md](MQTT.md) - phase and line voltages,
per-phase current, active/reactive/apparent power and power factor per phase and
total, frequency. 26 sensors.

The meter's own `*_meter` totals are not exposed: they read about a third of
reality. Values are signed - active/reactive power and power factor go negative
when the site exports.

A node publishes only when its Modbus read succeeded, so silence is a fault:
sensors go unavailable after 15 s (three cadences) without a message, even while
the retained status topic still says `online`.
