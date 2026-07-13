"""Config flow for SparkSync."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SparkSyncApi, SparkSyncAuthError, SparkSyncError
from .const import DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="http://localhost:4000"): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
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
                    title=f"SparkSync ({user_input[CONF_USERNAME]})", data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
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
