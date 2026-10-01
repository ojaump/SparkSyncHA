"""Config flow for SparkSync. Both modes are a broker and a base topic."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from . import broker
from .const import (
    CONF_BASE_TOPIC,
    CONF_MODE,
    CONF_TLS,
    CONF_WEBSOCKET,
    CONF_WS_PATH,
    DEFAULT_GATEWAY_TOPIC,
    DEFAULT_METER_TOPIC,
    DEFAULT_WS_PATH,
    DOMAIN,
    MODE_GATEWAY,
    MODE_METER,
)


def _schema(default_topic: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=443): int,
            # The site broker is MQTT over WebSocket; turn this off for a plain
            # TCP broker (Mosquitto add-on: core-mosquitto, port 1883, TLS off).
            vol.Required(CONF_WEBSOCKET, default=True): bool,
            vol.Optional(CONF_WS_PATH, default=DEFAULT_WS_PATH): str,
            vol.Required(CONF_TLS, default=True): bool,
            vol.Optional(CONF_USERNAME, default=""): str,
            vol.Optional(CONF_PASSWORD, default=""): str,
            vol.Required(CONF_BASE_TOPIC, default=default_topic): str,
        }
    )


class SparkSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["gateway", "meter"])

    async def async_step_gateway(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_broker_step(
            "gateway", MODE_GATEWAY, DEFAULT_GATEWAY_TOPIC, "SparkSync", user_input
        )

    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_broker_step(
            "meter", MODE_METER, DEFAULT_METER_TOPIC, "SparkSync meters", user_input
        )

    async def _async_broker_step(
        self,
        step_id: str,
        mode: str,
        default_topic: str,
        title: str,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self.hass.async_add_executor_job(broker.validate, user_input)
            if error:
                errors["base"] = error
            else:
                base = user_input[CONF_BASE_TOPIC].rstrip("/")
                host = user_input[CONF_HOST]
                await self.async_set_unique_id(f"{mode}::{host}::{base}".lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{title} ({host})",
                    data={**user_input, CONF_BASE_TOPIC: base, CONF_MODE: mode},
                )
        return self.async_show_form(
            step_id=step_id, data_schema=_schema(default_topic), errors=errors
        )
