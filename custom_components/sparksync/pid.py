"""PI(D) regulator holding grid export at a constant target.

Pure math, no Home Assistant imports, so it is testable on its own.

Process variable: grid export power (kW). Manipulated variable: the generator's
load-level-max (%), which is what `POST /load-level-max` accepts. The user's
"max percentage" is the upper clamp on that output.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEADBAND_PERCENT,
    DEFAULT_KD,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_MAX_PERCENT,
    DEFAULT_TARGET_KW,
    MAX_DT_S,
    MIN_WRITE_INTERVAL_S,
    RESYNC_INTERVAL_S,
)


@dataclass
class ExportPID:
    """Settings + loop state for one generator. Entities mutate the settings."""

    # Settings (owned by the number/switch entities).
    enabled: bool = False
    target_kw: float = DEFAULT_TARGET_KW
    max_percent: float = DEFAULT_MAX_PERCENT
    kp: float = DEFAULT_KP
    ki: float = DEFAULT_KI
    kd: float = DEFAULT_KD

    # Loop state.
    integral: float | None = None  # None = not running; also carries the steady-state output
    last_error: float | None = None
    last_step: float = 0.0
    last_written: int | None = None
    last_write: float = 0.0

    @property
    def running(self) -> bool:
        return self.integral is not None

    @property
    def at_max(self) -> bool:
        """Pinned at the user's ceiling — the generator cannot push export any higher."""
        return self.running and self.last_written is not None and self.last_written >= round(self.max_percent)

    def start(self, load_percent: float) -> None:
        """Bumpless transfer: seed the integral with where the generator already is."""
        self.integral = min(max(load_percent, 0.0), self.max_percent)
        self.last_error = None
        self.last_step = 0.0
        self.last_written = None

    def stop(self) -> None:
        self.integral = None
        self.last_error = None
        self.last_written = None

    def step(self, export_kw: float, now: float) -> int | None:
        """Advance the loop. Returns the load-level-max % to write, or None for no write.

        None means: not running, rate-limited, or the command has not moved.
        """
        if not self.enabled or self.integral is None:
            return None

        # dt from the real clock — the coordinator can be late, and HA can suspend.
        dt = 0.0 if not self.last_step else min(now - self.last_step, MAX_DT_S)
        self.last_step = now

        error = self.target_kw - export_kw  # under target => raise the generator
        proportional = self.kp * error
        derivative = (
            self.kd * (error - self.last_error) / dt
            if dt > 0 and self.last_error is not None
            else 0.0
        )
        self.last_error = error

        # Anti-windup: the integral carries the steady-state output, so clamping it
        # to the output range is enough — and it can unwind the moment error flips.
        if dt > 0:
            integral = self.integral + self.ki * error * dt
            self.integral = min(max(integral, 0.0), self.max_percent)

        output = min(max(proportional + self.integral + derivative, 0.0), self.max_percent)

        if now - self.last_write < MIN_WRITE_INTERVAL_S:
            return None  # the API allows 10 writes/min; stay well under it
        command = round(output)
        unchanged = (
            self.last_written is not None
            and abs(command - self.last_written) < DEADBAND_PERCENT
        )
        if unchanged and now - self.last_write < RESYNC_INTERVAL_S:
            return None
        self.last_write = now
        self.last_written = command
        return command
