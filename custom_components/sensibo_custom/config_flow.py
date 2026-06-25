"""Config flow for Sensibo Custom."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SensiboAuthError, SensiboClient, SensiboConnectionError, SensiboError
from .const import (
    AUTH_METHOD,
    AUTH_METHOD_ACCOUNT,
    AUTH_METHOD_API_KEY,
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Unable to connect to Sensibo."""


class InvalidAuth(Exception):
    """Invalid Sensibo authentication."""


AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(AUTH_METHOD, default=AUTH_METHOD_ACCOUNT): vol.In(
            {
                AUTH_METHOD_ACCOUNT: "Account login",
                AUTH_METHOD_API_KEY: "API key",
            }
        )
    }
)

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)

API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)


async def _validate_account(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate account credentials and return entry metadata."""
    session = async_get_clientsession(hass)
    client = SensiboClient(
        session,
        base_url=data[CONF_BASE_URL],
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
    )

    try:
        await client.async_login()
        devices = await client.async_get_devices()
        try:
            user = await client.async_get_user()
        except SensiboError:
            user = {}
    except SensiboAuthError as err:
        raise InvalidAuth from err
    except SensiboConnectionError as err:
        raise CannotConnect from err
    except SensiboError as err:
        raise CannotConnect from err

    account_id = user.get("id") or user.get("_id") or data[CONF_EMAIL].lower()
    title = user.get("email") or data[CONF_EMAIL]
    return {"unique_id": f"account:{account_id}", "title": title, "devices": len(devices)}


async def _validate_api_key(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate an API key and return entry metadata."""
    session = async_get_clientsession(hass)
    client = SensiboClient(
        session,
        base_url=data[CONF_BASE_URL],
        api_key=data[CONF_API_KEY],
    )

    try:
        devices = await client.async_get_devices()
        try:
            user = await client.async_get_user()
        except SensiboError:
            user = {}
    except SensiboAuthError as err:
        raise InvalidAuth from err
    except SensiboConnectionError as err:
        raise CannotConnect from err
    except SensiboError as err:
        raise CannotConnect from err

    account_id = user.get("id") or user.get("_id")
    if not account_id:
        account_id = hashlib.sha256(data[CONF_API_KEY].encode()).hexdigest()[:16]
    title = user.get("email") or "Sensibo"
    return {"unique_id": f"api_key:{account_id}", "title": title, "devices": len(devices)}


class SensiboCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Sensibo Custom config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose an auth method."""
        if user_input is not None:
            if user_input[AUTH_METHOD] == AUTH_METHOD_API_KEY:
                return await self.async_step_api_key()
            return await self.async_step_account()

        return self.async_show_form(step_id="user", data_schema=AUTH_SCHEMA)

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure account login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_account(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception while validating Sensibo account")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={**user_input, AUTH_METHOD: AUTH_METHOD_ACCOUNT},
                )

        return self.async_show_form(
            step_id="account", data_schema=ACCOUNT_SCHEMA, errors=errors
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure API key auth."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_api_key(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception while validating Sensibo API key")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={**user_input, AUTH_METHOD: AUTH_METHOD_API_KEY},
                )

        return self.async_show_form(
            step_id="api_key", data_schema=API_KEY_SCHEMA, errors=errors
        )
