"""Sensibo Custom integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SensiboAuthError, SensiboClient
from .const import (
    AUTH_METHOD,
    AUTH_METHOD_ACCOUNT,
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SensiboDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sensibo Custom from a config entry."""
    session = async_get_clientsession(hass)
    data = entry.data

    client = SensiboClient(
        session,
        base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        api_key=data.get(CONF_API_KEY),
        email=data.get(CONF_EMAIL),
        password=data.get(CONF_PASSWORD),
    )

    if data.get(AUTH_METHOD) == AUTH_METHOD_ACCOUNT:
        try:
            await client.async_login()
        except SensiboAuthError as err:
            raise ConfigEntryAuthFailed from err

    coordinator = SensiboDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
