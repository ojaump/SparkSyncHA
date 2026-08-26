"""Master switch for export regulation. Off unless the user turns it on."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SparkSyncConfigEntry, SparkSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SparkSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(SparkSyncExportSwitch(c) for c in entry.runtime_data)


class SparkSyncExportSwitch(RestoreEntity, SwitchEntity):
    """Arms the PID. The loop itself runs on the coordinator's poll."""

    _attr_has_entity_name = True
    _attr_name = "Export regulation"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, coordinator: SparkSyncCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device['mac_address']}_export_regulation"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        self.coordinator.pid.enabled = state is not None and state.state == "on"

    @property
    def is_on(self) -> bool:
        return self.coordinator.pid.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # `status` says why the loop is or is not writing; `at_max_percent` true
        # means the ceiling, not the tuning, is holding export below target.
        pid = self.coordinator.pid
        return {
            "status": pid.status,
            "export_kw": self.coordinator.measured_export_kw(),
            "target_kw": pid.target_kw,
            "load_level_max_percent": pid.last_written,
            "at_max_percent": pid.at_max,
            "integral_percent": None if pid.integral is None else round(pid.integral, 2),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.pid.enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Leave load-level-max where it is; the operator decides what happens next.
        self.coordinator.pid.enabled = False
        self.coordinator.pid.stop()
        self.async_write_ha_state()
