# SparkSync for Home Assistant

Custom integration for the SparkSync generator gateway API. Exposes engine
telemetry and power production as sensors for every device your account can
read.

## Install

1. HACS → Integrations → Custom repositories → add this repo (type: Integration).
2. Install **SparkSync**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → SparkSync.
4. Enter the API URL (e.g. `http://localhost:4000`), username, and password.

## Sensors

Per device (canonical fields, DSE and EasyGen):

- **Power**: generator power, frequency, voltage, current, power factor, load %, mains power
- **Engine**: speed, oil pressure/temperature/level, coolant temperature/level, battery voltage, fuel rate
- **Accumulated**: generated energy (kWh — usable in the Energy dashboard), engine run time, engine starts
- **Status**: control mode

Polls `/info` every 15 s per device.
