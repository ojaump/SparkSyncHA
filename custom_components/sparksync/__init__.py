"""The SparkSync integration.

Everything arrives over MQTT: generator gateways publish one JSON section per
topic at 1 Hz, meter nodes publish a whole reading every 5 s. One config entry
is one broker connection; devices are discovered from the topics they appear on.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .broker import BrokerHub
from .const import CONF_MODE, MODE_METER
from .gateway import SparkSyncGatewayCoordinator
from .meter import SparkSyncMeterCoordinator

PLATFORMS = [Platform.SENSOR]

type SparkSyncConfigEntry = ConfigEntry[BrokerHub]


async def async_setup_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    coordinator_class = (
        SparkSyncMeterCoordinator
        if entry.data[CONF_MODE] == MODE_METER
        else SparkSyncGatewayCoordinator
    )
    hub = BrokerHub(hass, entry, coordinator_class)
    await hub.async_start()
    entry.async_on_unload(hub.async_stop)
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
