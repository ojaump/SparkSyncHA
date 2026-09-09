"""SparkSync sensors — engine data and power production."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SparkSyncConfigEntry, SparkSyncCoordinator
from .const import CONF_MODE, MODE_MQTT
from .meter import SparkSyncMeterCoordinator, SparkSyncMeterHub


@dataclass(frozen=True, kw_only=True)
class SparkSyncSensorDescription(SensorEntityDescription):
    """Adds the /info section and field the value lives in."""

    section: str
    field: str


# Canonical fields only — present on both DSE and EasyGen controllers.
SENSORS: tuple[SparkSyncSensorDescription, ...] = (
    # Power production
    SparkSyncSensorDescription(
        key="generator_total_power_w",
        name="Generator power",
        section="generator",
        field="total_power_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="generator_frequency_hz",
        name="Generator frequency",
        section="generator",
        field="frequency_hz",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="generator_av_wye_voltage_v",
        name="Generator voltage",
        section="generator",
        field="av_wye_voltage_v",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="generator_av_current_a",
        name="Generator current",
        section="generator",
        field="av_current_a",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="generator_power_factor",
        name="Power factor",
        section="generator",
        field="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="generator_percent_full_power",
        name="Load",
        section="generator",
        field="percent_full_power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="mains_total_power_w",
        name="Mains power",
        section="mains",
        field="total_power_w",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Engine
    SparkSyncSensorDescription(
        key="engine_speed_rpm",
        name="Engine speed",
        section="engine",
        field="engine_speed_rpm",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_oil_pressure_kpa",
        name="Oil pressure",
        section="engine",
        field="oil_pressure_kpa",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_coolant_temperature_c",
        name="Coolant temperature",
        section="engine",
        field="coolant_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_oil_temperature_c",
        name="Oil temperature",
        section="engine",
        field="oil_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_oil_level_percent",
        name="Oil level",
        section="engine",
        field="oil_level_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_coolant_level_percent",
        name="Coolant level",
        section="engine",
        field="coolant_level_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_battery_voltage_v",
        name="Battery voltage",
        section="engine",
        field="battery_voltage_v",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SparkSyncSensorDescription(
        key="engine_fuel_consumption_lph",
        name="Fuel rate",
        section="engine",
        field="fuel_consumption_lph",
        native_unit_of_measurement="L/h",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Accumulated
    SparkSyncSensorDescription(
        key="accumulated_gen_positive_kwh",
        name="Generated energy",
        section="accumulated",
        field="gen_positive_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SparkSyncSensorDescription(
        key="accumulated_engine_run_time_seconds",
        name="Engine run time",
        section="accumulated",
        field="engine_run_time_seconds",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SparkSyncSensorDescription(
        key="accumulated_number_of_starts",
        name="Engine starts",
        section="accumulated",
        field="number_of_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Status
    SparkSyncSensorDescription(
        key="status_control_mode",
        name="Control mode",
        section="status",
        field="control_mode",
    ),
)


PHASES = (("a", "L1"), ("b", "L2"), ("c", "L3"))
LINES = (("ab", "L1-L2"), ("bc", "L2-L3"), ("ca", "L3-L1"))


def _meter(key: str, name: str, unit=None, device_class=None) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT,
    )


# The flat MQTT payload, minus `id` and the meter's own broken totals (MQTT.md).
# Active/reactive power and power factor go negative when the site exports.
METER_SENSORS: tuple[SensorEntityDescription, ...] = (
    *(
        _meter(f"u{p}", f"Voltage {n}", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE)
        for p, n in PHASES
    ),
    *(
        _meter(f"u{p}", f"Voltage {n}", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE)
        for p, n in LINES
    ),
    *(
        _meter(f"i{p}", f"Current {n}", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT)
        for p, n in PHASES
    ),
    *(
        _meter(f"p{p}", f"Active power {n}", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER)
        for p, n in PHASES
    ),
    _meter("p", "Active power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    *(
        _meter(
            f"q{p}",
            f"Reactive power {n}",
            UnitOfReactivePower.KILO_VOLT_AMPERE_REACTIVE,
            SensorDeviceClass.REACTIVE_POWER,
        )
        for p, n in PHASES
    ),
    _meter(
        "q",
        "Reactive power",
        UnitOfReactivePower.KILO_VOLT_AMPERE_REACTIVE,
        SensorDeviceClass.REACTIVE_POWER,
    ),
    *(
        _meter(
            f"s{p}",
            f"Apparent power {n}",
            UnitOfApparentPower.KILO_VOLT_AMPERE,
            SensorDeviceClass.APPARENT_POWER,
        )
        for p, n in PHASES
    ),
    _meter(
        "s", "Apparent power", UnitOfApparentPower.KILO_VOLT_AMPERE, SensorDeviceClass.APPARENT_POWER
    ),
    *(
        _meter(f"pf{p}", f"Power factor {n}", device_class=SensorDeviceClass.POWER_FACTOR)
        for p, n in PHASES
    ),
    _meter("pf", "Power factor", device_class=SensorDeviceClass.POWER_FACTOR),
    _meter("freq", "Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SparkSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_MODE) == MODE_MQTT:
        _setup_meters(hass, entry, async_add_entities)
        return
    async_add_entities(
        SparkSyncSensor(coordinator, description)
        for coordinator in entry.runtime_data
        for description in SENSORS
    )


@callback
def _setup_meters(
    hass: HomeAssistant,
    entry: SparkSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Nodes appear as they publish - the retained status topic reveals them first."""
    hub: SparkSyncMeterHub = entry.runtime_data
    seen: set[str] = set()

    @callback
    def _discover() -> None:
        for mac, coordinator in hub.coordinators.items():
            if mac in seen:
                continue
            seen.add(mac)
            async_add_entities(
                SparkSyncMeterSensor(coordinator, description)
                for description in METER_SENSORS
            )

    entry.async_on_unload(
        async_dispatcher_connect(hass, hub.new_node_signal, _discover)
    )
    _discover()


class SparkSyncSensor(CoordinatorEntity[SparkSyncCoordinator], SensorEntity):
    """One canonical /info field."""

    _attr_has_entity_name = True
    entity_description: SparkSyncSensorDescription

    def __init__(
        self,
        coordinator: SparkSyncCoordinator,
        description: SparkSyncSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device['mac_address']}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        # Gateway offline => the API keeps serving the last snapshot forever.
        return super().available and self.coordinator.data_is_fresh

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        section = data.get(self.entity_description.section) or {}
        return section.get(self.entity_description.field)


class SparkSyncMeterSensor(CoordinatorEntity[SparkSyncMeterCoordinator], SensorEntity):
    """One key of the flat meter payload."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SparkSyncMeterCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        # A node only publishes when its Modbus read worked; silence means stale.
        return self.coordinator.data_is_fresh

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self.entity_description.key)
