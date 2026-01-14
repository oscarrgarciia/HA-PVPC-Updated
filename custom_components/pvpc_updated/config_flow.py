"""Config flow for PVPC Updated integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlowWithReload
from homeassistant.const import CONF_NAME, CONF_API_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import SOURCE_REAUTH

from .aiopvpc import PVPCData, DEFAULT_POWER_KW
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    DEFAULT_TARIFF,
    ATTR_POWER,
    ATTR_POWER_P3,
    ATTR_TARIFF,
    CONF_USE_API_TOKEN,
    VALID_POWER,
    VALID_TARIFF,
)

_MAIL_TO_LINK = "[consultasios@ree.es](mailto:consultasios@ree.es?subject=Personal%20token%20request)"


class PVPCOptionsFlowHandler(OptionsFlowWithReload):
    """Handle PVPC options flow."""

    _power: float | None = None
    _power_p3: float | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        options = self.config_entry.options
        data = self.config_entry.data
        power = options.get(ATTR_POWER, data.get(ATTR_POWER))
        power_p3 = options.get(ATTR_POWER_P3, data.get(ATTR_POWER_P3))
        api_token = options.get(CONF_API_TOKEN, data.get(CONF_API_TOKEN))
        use_api_token = api_token is not None

        schema = vol.Schema(
            {
                vol.Required(ATTR_POWER, default=power): VALID_POWER,
                vol.Required(ATTR_POWER_P3, default=power_p3): VALID_POWER,
                vol.Required(CONF_USE_API_TOKEN, default=use_api_token): bool,
            }
        )

        if user_input is not None:
            self._power = user_input[ATTR_POWER]
            self._power_p3 = user_input[ATTR_POWER_P3]
            if user_input[CONF_USE_API_TOKEN]:
                return await self.async_step_api_token(user_input)
            return self.async_create_entry(
                title="",
                data={
                    ATTR_POWER: self._power,
                    ATTR_POWER_P3: self._power_p3,
                    CONF_API_TOKEN: None,
                },
            )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_api_token(self, user_input: dict[str, Any] | None = None):
        """Handle optional API token step for extra sensors."""
        api_token = user_input.get(CONF_API_TOKEN) if user_input else None
        if user_input is not None and api_token:
            return self.async_create_entry(
                title="",
                data={
                    ATTR_POWER: self._power,
                    ATTR_POWER_P3: self._power_p3,
                    CONF_API_TOKEN: api_token,
                },
            )

        default_token = self.config_entry.options.get(
            CONF_API_TOKEN, self.config_entry.data.get(CONF_API_TOKEN)
        )

        schema = vol.Schema({vol.Required(CONF_API_TOKEN, default=default_token): str})

        return self.async_show_form(
            step_id="api_token",
            data_schema=schema,
            description_placeholders={"mail_to_link": _MAIL_TO_LINK},
        )


class TariffSelectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for PVPC Updated."""

    VERSION = 1
    _name: str | None = None
    _tariff: str | None = None
    _power: float | None = None
    _power_p3: float | None = None
    _use_api_token: bool = False
    _api_token: str | None = None
    _api: PVPCData | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return the options flow handler."""
        return PVPCOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Initial configuration step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[ATTR_TARIFF])
            self._abort_if_unique_id_configured()

            self._name = user_input[CONF_NAME]
            self._tariff = user_input[ATTR_TARIFF]
            self._power = user_input[ATTR_POWER]
            self._power_p3 = user_input[ATTR_POWER_P3]
            self._use_api_token = user_input[CONF_USE_API_TOKEN]

            if self._use_api_token:
                return await self.async_step_api_token()
            return self.async_create_entry(
                title=self._name,
                data={
                    CONF_NAME: self._name,
                    ATTR_TARIFF: self._tariff,
                    ATTR_POWER: self._power,
                    ATTR_POWER_P3: self._power_p3,
                    CONF_API_TOKEN: None,
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(ATTR_TARIFF, default=DEFAULT_TARIFF): VALID_TARIFF,
                vol.Required(ATTR_POWER, default=DEFAULT_POWER_KW): VALID_POWER,
                vol.Required(ATTR_POWER_P3, default=DEFAULT_POWER_KW): VALID_POWER,
                vol.Required(CONF_USE_API_TOKEN, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_api_token(self, user_input: dict[str, Any] | None = None):
        """Optional step to set API token."""
        if user_input is not None:
            self._api_token = user_input[CONF_API_TOKEN]
            return await self._async_verify("api_token")

        schema = vol.Schema({vol.Required(CONF_API_TOKEN, default=self._api_token): str})
        return self.async_show_form(
            step_id="api_token",
            data_schema=schema,
            description_placeholders={"mail_to_link": _MAIL_TO_LINK},
        )

    async def _async_verify(self, step_id: str):
        """Verify API token if used."""
        errors: dict[str, str] = {}
        auth_ok = True

        if self._use_api_token:
            if not self._api:
                self._api = PVPCData(session=async_get_clientsession(self.hass))
            auth_ok = await self._api.check_api_token(dt_util.utcnow(), self._api_token)

        if not auth_ok:
            errors["base"] = "invalid_auth"
            return self.async_show_form(step_id=step_id, errors=errors)

        data = {
            CONF_NAME: self._name,
            ATTR_TARIFF: self._tariff,
            ATTR_POWER: self._power,
            ATTR_POWER_P3: self._power_p3,
            CONF_API_TOKEN: self._api_token if self._use_api_token else None,
        }

        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(None, data=data)

        assert self._name is not None
        return self.async_create_entry(title=self._name, data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Re-authentication step."""
        self._api_token = entry_data.get(CONF_API_TOKEN)
        self._use_api_token = self._api_token is not None
        self._name = entry_data[CONF_NAME]
        self._tariff = entry_data[ATTR_TARIFF]
        self._power = entry_data[ATTR_POWER]
        self._power_p3 = entry_data[ATTR_POWER_P3]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm re-authentication."""
        schema = vol.Schema(
            {
                vol.Required(CONF_USE_API_TOKEN, default=self._use_api_token): bool,
                vol.Optional(CONF_API_TOKEN, default=self._api_token): str,
            }
        )
        if user_input:
            self._api_token = user_input.get(CONF_API_TOKEN)
            self._use_api_token = user_input[CONF_USE_API_TOKEN]
            return await self._async_verify("reauth_confirm")
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema)
