"""Config flow for SparkSync."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_URL,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import meter
from .api import SparkSyncApi, SparkSyncAuthError, SparkSyncError
from .const import (
    CONF_BASE_TOPIC,
    CONF_MODE,
    CONF_TLS,
    CONF_WEBSOCKET,
    CONF_WS_PATH,
    DEFAULT_BASE_TOPIC,
    DEFAULT_WS_PATH,
    DOMAIN,
    MODE_API,
    MODE_MQTT,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="http://localhost:4000"): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

MQTT_SCHEMA = vol.Schema(
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
        vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
    }
)


class SparkSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def _validate(self, url: str, username: str, password: str) -> str | None:
        """Try to log in; return an error key or None."""
        api = SparkSyncApi(async_get_clientsession(self.hass), url, username, password)
        try:
            await api.async_login()
        except SparkSyncAuthError:
            return "invalid_auth"
        except SparkSyncError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["gateway", "mqtt"])

    async def async_step_gateway(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._validate(
                user_input[CONF_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_URL]}::{user_input[CONF_USERNAME]}".lower()
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"SparkSync ({user_input[CONF_USERNAME]})",
                    data={**user_input, CONF_MODE: MODE_API},
                )
        return self.async_show_form(
            step_id="gateway", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_mqtt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self.hass.async_add_executor_job(meter.validate, user_input)
            if error:
                errors["base"] = error
            else:
                base = user_input[CONF_BASE_TOPIC].rstrip("/")
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}::{base}".lower()
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"SparkSync meters ({user_input[CONF_HOST]})",
                    data={**user_input, CONF_BASE_TOPIC: base, CONF_MODE: MODE_MQTT},
                )
        return self.async_show_form(
            step_id="mqtt", data_schema=MQTT_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await self._validate(
                entry.data[CONF_URL],
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
