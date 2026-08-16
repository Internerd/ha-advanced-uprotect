"""Config flow for UniFi Protect Zone Tracking."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from uiprotect import ProtectApiClient
from uiprotect.exceptions import ClientError, NotAuthorized
import voluptuous as vol

from .const import (
    CONF_AUTO_OFF_SECONDS,
    CONF_VERIFY_SSL,
    DEFAULT_AUTO_OFF_SECONDS,
    DEFAULT_PORT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_AUTO_OFF_SECONDS,
    MIN_AUTO_OFF_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AUTO_OFF_SECONDS, default=DEFAULT_AUTO_OFF_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_AUTO_OFF_SECONDS, max=MAX_AUTO_OFF_SECONDS),
        )
    }
)


class UnifiProtectZonesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Protect Zone Tracking."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return UnifiProtectZonesOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api = ProtectApiClient(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                verify_ssl=user_input[CONF_VERIFY_SSL],
                session=async_create_clientsession(
                    self.hass, verify_ssl=user_input[CONF_VERIFY_SSL]
                ),
            )
            try:
                bootstrap = await api.update()
            except NotAuthorized:
                errors["base"] = "invalid_auth"
            except ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating Protect connection")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(bootstrap.nvr.mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=bootstrap.nvr.name or user_input[CONF_HOST],
                    data=user_input,
                )
            finally:
                await api.close_session()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )


class UnifiProtectZonesOptionsFlow(OptionsFlow):
    """Let the user tune how long the per-zone binary sensors stay on."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
