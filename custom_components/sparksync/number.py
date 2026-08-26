"""Export-regulation setpoints and PID gains."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SparkSyncConfigEntry, SparkSyncCoordinator


@dataclass(frozen=True, kw_only=True)
class SparkSyncNumberDescription(NumberEntityDescription):
    """Adds the ExportPID attribute this number writes to."""

    attr: str


NUMBERS: tuple[SparkSyncNumberDescription, ...] = (
    SparkSyncNumberDescription(
        key="export_target_kw",
        name="Export target",
        attr="target_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0,
        native_max_value=5000,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    SparkSyncNumberDescription(
        key="export_max_percent",
        name="Max generator load",
        attr="max_percent",
        native_unit_of_measurement="%",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    # Gains: no rated power is known here, so the loop has to be tuned on site.
    SparkSyncNumberDescription(
        key="export_kp", name="Export PID Kp", attr="kp",
        native_min_value=0, native_max_value=5, native_step=0.001, mode=NumberMode.BOX,
    ),
    SparkSyncNumberDescription(
        key="export_ki", name="Export PID Ki", attr="ki",
        native_min_value=0, native_max_value=1, native_step=0.001, mode=NumberMode.BOX,
    ),
    SparkSyncNumberDescription(
        key="export_kd", name="Export PID Kd", attr="kd",
        native_min_value=0, native_max_value=5, native_step=0.001, mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SparkSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        SparkSyncNumber(coordinator, description)
        for coordinator in entry.runtime_data
        for description in NUMBERS
    )


class SparkSyncNumber(RestoreNumber):
    """One tunable on the export PID. Stays available when telemetry goes stale."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    entity_description: SparkSyncNumberDescription

    def __init__(
        self,
        coordinator: SparkSyncCoordinator,
        description: SparkSyncNumberDescription,
    ) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device['mac_address']}_{description.key}"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            setattr(self.coordinator.pid, self.entity_description.attr, last.native_value)

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator.pid, self.entity_description.attr)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.coordinator.pid, self.entity_description.attr, value)
        # Changing a gain or the ceiling mid-flight would otherwise keep steering
        # from an integral built for the old settings.
        if self.coordinator.pid.running:
            self.coordinator.pid.start(self.coordinator.pid.integral)
        self.async_write_ha_state()
