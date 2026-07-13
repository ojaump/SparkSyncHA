# SparkSync API Routes

Base URL: `http://localhost:4000`

All responses are JSON. Every route except `/health` and the public auth routes requires `Authorization: Bearer <access_token>`.

---

## Public

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + MQTT status) |

### GET /health
```json
// 200
{
  "status": "healthy",
  "services": {
    "database": { "status": "up", "latency_ms": 3 },
    "mqtt": { "status": "connected" }
  }
}

// 503 — DB down
{
  "status": "unhealthy",
  "services": {
    "database": { "status": "down", "latency_ms": null },
    "mqtt": { "status": "disconnected" }
  }
}
```

---

## Auth

| Method | Path | Rate limit | Auth | Description |
|--------|------|-----------|------|-------------|
| POST | `/auth/register` | 5/min | — | Create account |
| POST | `/auth/login` | 10/min | — | Login |
| POST | `/auth/refresh` | — | — | Rotate tokens |
| POST | `/auth/logout` | — | Bearer | Revoke refresh token |
| POST | `/auth/change-password` | 5/min | Bearer | Change own password |
| POST | `/auth/forgot-password` | 3/min | — | Email a reset link |
| POST | `/auth/reset-password` | 5/min | — | Reset via emailed token |

### POST /auth/register
```json
// Request
{ "username": "joao", "password": "mypassword", "email": "joao@example.com" }

// 201
{ "message": "User created", "username": "joao", "email": "joao@example.com" }

// 409
{ "message": "Username or email already taken", "statusCode": 409 }
```

### POST /auth/login
```json
// Request
{ "username": "joao", "password": "mypassword" }

// 200
{ "access_token": "eyJ...", "refresh_token": "AaBb..." }

// 401
{ "message": "Invalid credentials", "statusCode": 401 }
```

### POST /auth/refresh
```json
// Request
{ "refresh_token": "AaBb..." }

// 200 — old token invalidated, new pair issued
{ "access_token": "eyJ...", "refresh_token": "CcDd..." }

// 401 — expired or already used
{ "message": "Invalid or expired refresh token", "statusCode": 401 }
```

### POST /auth/logout
```json
// Request
{ "refresh_token": "AaBb..." }

// 200
{ "message": "Logged out" }
```

### POST /auth/change-password
```json
// Request
{ "current_password": "old", "new_password": "new" }

// 200
{ "message": "Password changed" }
```

### POST /auth/forgot-password
```json
// Request
{ "email": "joao@example.com" }

// 200 — always, whether or not the email exists
{ "message": "If that email is registered, a reset link was sent" }
```

### POST /auth/reset-password
```json
// Request
{ "token": "<from email>", "new_password": "new" }

// 200
{ "message": "Password reset successfully" }
```

---

## Devices

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| POST | `/devices` | authenticated | Register device |
| GET | `/devices` | authenticated | List accessible devices |
| GET | `/devices/:id` | any access | Get device |
| PUT | `/devices/:id` | owner | Rename device |
| DELETE | `/devices/:id` | owner | Delete device |
| GET | `/devices/:id/members` | owner | List shared users |
| POST | `/devices/:id/members` | owner | Share device |
| PUT | `/devices/:id/members/:userId` | owner | Update permissions |
| DELETE | `/devices/:id/members/:userId` | owner | Revoke access |

### POST /devices
```json
// Request
{ "name": "Generator 1", "mac_address": "a1b2c3d4e5f6" }

// 201
{
  "id": 1,
  "name": "Generator 1",
  "mac_address": "a1b2c3d4e5f6",
  "owner_id": 42,
  "created_at": "2026-04-13T10:00:00.000Z"
}

// 409
{ "message": "A device with that MAC address is already registered", "statusCode": 409 }
```

### GET /devices
```json
// 200
[
  {
    "id": 1,
    "name": "Generator 1",
    "mac_address": "a1b2c3d4e5f6",
    "owner_id": 42,
    "created_at": "2026-04-13T10:00:00.000Z",
    "is_owner": true,
    "can_read": true,
    "can_command": true,
    "can_configure": true
  }
]
```

### GET /devices/:id
Same shape as the list entry, single object. `404` if not found or no access.

### PUT /devices/:id
```json
// Request
{ "name": "Main Generator" }
// 200 — updated device object
```

### DELETE /devices/:id
```json
// 200
{ "message": "Device 1 deleted" }
```

### GET /devices/:id/members
```json
// 200
[
  {
    "user_id": 7,
    "username": "maria",
    "can_read": true,
    "can_command": false,
    "can_configure": false,
    "granted_at": "2026-04-13T10:00:00.000Z"
  }
]
```

### POST /devices/:id/members
```json
// Request
{ "username": "maria", "can_read": true, "can_command": false, "can_configure": false }
// 200 — permission object (upserts if already shared)
```

### PUT /devices/:id/members/:userId
```json
// Request — omitted fields keep current value
{ "can_command": true }
// 200 — updated permission object
```

### DELETE /devices/:id/members/:userId
```json
// 200
{ "message": "Access revoked for user 7 on device 1" }
```

---

## Generator

| Method | Path | Rate limit | Permission | Description |
|--------|------|-----------|-----------|-------------|
| GET | `/info?id=` | 250/min | can_read | Latest telemetry snapshot (unified DSE/EasyGen) |
| GET | `/commands` | — | authenticated | List valid commands |
| POST | `/command` | 10/min | can_command | Send control command |
| POST | `/status` | 10/min | can_command | Legacy alias of `/command` (field `mode`) |
| GET | `/command/ack?request_id=&id=` | — | can_read | Poll command acknowledgement |
| GET | `/load-level-max?id=` | — | can_read | Get current max load level |
| POST | `/load-level-max` | 10/min | can_configure | Set max load level |
| GET | `/load-level-max/ack?request_id=&id=` | — | can_read | Poll load-level acknowledgement |
| POST | `/setpoint` | 10/min | can_configure | Set an EasyGen setpoint |
| GET | `/setpoint/ack?request_id=&id=` | — | can_read | Poll setpoint acknowledgement |
| GET | `/errors?id=` | — | can_read | Latest gateway error report |
| GET | `/health?id=` | — | can_read | Latest gateway health snapshot |
| POST | `/ota` | 5/min | can_configure | Trigger OTA firmware/spiffs update |
| GET | `/events?id=&limit=&before_id=` | — | can_read | Device event log (paginated) |

### GET /info

Returns the latest value of every telemetry section. Payloads from both
controller types (DSE and EasyGen) are normalized at ingest into one canonical
vocabulary — the fields below are present **regardless of controller**.
Controller-specific extras are preserved alongside them; branch on
`_meta.controller` (`"dse"` | `"easygen"`) only if you need those extras.
Any value the controller did not report is `null`.

Canonical fields guaranteed on both controllers:

| Section | Canonical fields (both controllers) |
|---------|-------------------------------------|
| `generator` / `mains` / `bus` | `frequency_hz`, `l{1,2,3}_n_voltage_v`, `l1_l2/l2_l3/l3_l1_voltage_v`, `total_power_w` = `total_watts_w`, `total_var` = `total_reactive_var`, `total_va`, `power_factor`, `av_wye_voltage_v`, `av_delta_voltage_v`, `av_current_a` |
| `generator` only | `percent_full_power` (derived from `rated_active_power_kw` on EasyGen) |
| `engine` | `engine_speed_rpm`, `oil_pressure_kpa`, `coolant_temperature_c`, `oil_temperature_c`, `oil_level_percent`, `coolant_level_percent`, `battery_voltage` = `battery_voltage_v`, `fuel_consumption_lph` = `fuel_rate_lph`, `inlet_manifold_temp_1_c` = `inlet_manifold_temp_c`, `exhaust_temp_1_c` = `exhaust_gas_temp_c`, `turbo_pressure_1_kpa` = `boost_pressure_kpa` |
| `accumulated` | `number_of_starts` = `engine_starts`, `engine_run_time_seconds` = `gen_hours_of_operation_h` (unit-converted), `gen_positive_kwh` = `gen_real_energy_mwh` (unit-converted) |
| `alarms` | `named[]` (`{index, name, severity}`), `unnamed[]`, `active[]` — all three arrays always present |
| all sections | `ts`, `controller_online`, `last_modbus_ok_ms`, `last_modbus_ok_ts`, `_meta` |

Controller-specific extras (not normalized, may be absent):
- **DSE**: `status.state_machine_status`, `status.governor_output_percent`, `status.avr_output_percent`, per-phase `l{1,2,3}_watts_w`, `earth_current_a`, `phase_rotation`, `percent_full_var`, `fuel_level_percent`, dual-sensor `*_2_*` engine fields, `gen_negative_kwh`, `gen_kva_hours`, `gen_kvar_hours`, `mains_*_kwh`, `fuel_used_litres`
- **EasyGen**: `status.operation_mode`, `status.gcb_closed`, `status.mcb_closed`, `status.sync_*`, `status.crank_active`, `status.cooldown_active`, `generator.setpoint_{power_kw,pf,freq_hz,voltage_v}`, `generator.rated_active_power_kw`, `engine.engine_hours_h`, `engine.pickup_speed_rpm`, `accumulated.hours_until_maintenance_h`

```json
// 200 (EasyGen example, trimmed — DSE has identical canonical fields)
{
  "status": {
    "ts": 1783365156,
    "controller_online": true,
    "control_mode": "AUTO",
    "operation_mode": "In operation",
    "_meta": { "controller": "easygen", "received_at": 1783365156 }
  },
  "engine": {
    "engine_speed_rpm": 1800,
    "battery_voltage_v": 28.1,
    "battery_voltage": 28.1,
    "oil_pressure_kpa": 350,
    "coolant_temperature_c": 82
  },
  "generator": {
    "frequency_hz": 59.96,
    "av_wye_voltage_v": 226.5,
    "av_current_a": 223.95,
    "total_power_w": 144799,
    "total_watts_w": 144799,
    "total_var": 41371,
    "total_va": 150593,
    "power_factor": 0.962,
    "percent_full_power": 72.4
  },
  "mains": { "frequency_hz": 59.96, "total_power_w": -48141, "power_factor": 0.854 },
  "bus": { "frequency_hz": 59.96 },
  "accumulated": {
    "number_of_starts": 11858,
    "engine_run_time_seconds": 96194700,
    "gen_positive_kwh": 2287869.87,
    "gen_hours_of_operation_h": 26720.75
  },
  "alarms": { "named": [], "unnamed": [], "active": [] },
  "_meta": {
    "is_online": true,
    "controller_online": true,
    "controller": "easygen",
    "last_modbus_ok_ts": 1783365155,
    "last_seen": 1783365156
  }
}

// 503 — no MQTT data received yet for this device
{ "message": "No telemetry received yet for device 1 — ensure the gateway is online and publishing to the MQTT broker", "statusCode": 503 }
```

Top-level `_meta`: `is_online` (gateway published within the last 120 s),
`controller_online` (controller reachable over Modbus), `controller`,
`last_modbus_ok_ts`, `last_seen`.

### GET /commands
```json
// 200
{
  "commands": [
    "stop", "auto", "manual", "test_on_load", "start",
    "mute_alarm", "reset_alarms", "reset_all_alarms",
    "transfer_to_generator", "transfer_to_mains",
    "lock_controls", "unlock_controls", "lamp_test",
    "throttle_up", "throttle_down"
  ]
}
```

### POST /command
```json
// Request
{ "id": 1, "command": "auto" }

// 200
{ "message": "Command 'auto' sent to device 1", "request_id": "a3f2c1d4-..." }

// 400
{ "message": "Unknown command 'foo'", "statusCode": 400 }

// 403
{ "message": "can_command permission required for this device", "statusCode": 403 }
```

### POST /status *(legacy)*
```json
// Request — same as /command but field is `mode`
{ "id": 1, "mode": "auto" }
// 200 — same response as /command
```

### GET /command/ack
```json
// 200 — still waiting for device ACK
{ "request_id": "a3f2c1d4-...", "status": "pending" }

// 200 — success
{ "request_id": "a3f2c1d4-...", "status": "success", "success": true, "command": "auto", "error": null }

// 200 — device rejected
{ "request_id": "a3f2c1d4-...", "status": "error", "success": false, "command": "auto", "error": "Generator not ready" }
```
ACKs expire from the store after 5 minutes; an expired or unknown `request_id` reads as `pending`.

### GET /load-level-max
```json
// 200
{ "value_percent": 80 }

// 503
{ "message": "Load level max has not been received for device 1", "statusCode": 503 }
```

### POST /load-level-max
```json
// Request — value 0–100
{ "id": 1, "value": 75 }

// 200
{ "message": "Load level max set to 75% for device 1", "request_id": "b4e5f6a7-..." }
```

### GET /load-level-max/ack
```json
// 200 — pending / done
{ "request_id": "b4e5f6a7-...", "status": "pending" }
{ "request_id": "b4e5f6a7-...", "status": "success", "success": true, "value": 75 }
```

### POST /setpoint
EasyGen only. `name` ∈ `power_kw` | `pf` | `freq_hz` | `voltage_v`.
```json
// Request
{ "id": 1, "name": "power_kw", "value": 150 }

// 200
{ "message": "Setpoint 'power_kw' set to 150 for device 1", "request_id": "c5d6e7f8-..." }
```

### GET /setpoint/ack
```json
// 200 — pending / done
{ "request_id": "c5d6e7f8-...", "status": "pending" }
{ "request_id": "c5d6e7f8-...", "status": "success", "success": true, "name": "power_kw", "value": 150, "error": null }
```

### GET /errors
```json
// 200 — latest raw error report published by the gateway
{ "ts": 1783365156, "errors": [ ... ] }

// 503
{ "message": "No error data received yet for device 1", "statusCode": 503 }
```

### GET /health (generator)
```json
// 200
{
  "ts": 1783365156,
  "uptime_s": 31070,
  "free_heap": 123456,
  "rssi": -61,
  "local_connected": true,
  "aws_connected": false,
  "buffer_ready": true
}

// 503
{ "message": "No health data received yet for device 1", "statusCode": 503 }
```

### POST /ota
URL must be HTTPS and its hostname must be in `OTA_ALLOWED_HOSTS`.
```json
// Request
{ "id": 1, "url": "https://firmware.example.com/fw.bin", "type": "firmware" }

// 200
{ "message": "OTA update (firmware) triggered for device 1", "request_id": "d6e7f8a9-..." }

// 400 — host not allowed / invalid URL
// 503 — OTA_ALLOWED_HOSTS not configured
```

### GET /events
`limit` 1–200 (default 50); pass `before_id` from the previous page to paginate.
```json
// 200
{
  "events": [
    {
      "id": 321,
      "event_type": "command_sent",
      "message": "joao sent the AUTO command",
      "actor_id": 42,
      "actor_username": "joao",
      "metadata": { "command": "auto", "request_id": "a3f2c1d4-..." },
      "occurred_at": "2026-07-06T14:00:00.000Z"
    }
  ],
  "has_more": true,
  "next_before_id": 300
}
```
Event types: `command_sent`, `setpoint_changed`, `alarm_triggered`, `alarm_cleared`, `engine_anomaly`, `physical_command`.

---

## Error format

All errors follow the NestJS default shape:

```json
{
  "statusCode": 403,
  "message": "can_read permission required for this device",
  "error": "Forbidden"
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation failure |
| 401 | Missing or expired token |
| 403 | Valid token but insufficient permission |
| 404 | Resource not found or no access |
| 409 | Conflict (duplicate username, MAC, etc.) |
| 429 | Rate limit exceeded |
| 503 | Dependency unavailable (DB down, no MQTT data yet) |
