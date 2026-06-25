"""Data coordinator for Sensibo Custom."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SensiboApiError, SensiboAuthError, SensiboClient, SensiboConnectionError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SensiboDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator that keeps the Sensibo pod list fresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SensiboClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch devices from Sensibo."""
        try:
            devices = await self.client.async_get_devices()
        except SensiboAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (SensiboApiError, SensiboConnectionError) as err:
            raise UpdateFailed(str(err)) from err

        return {
            str(device["id"]): device
            for device in devices
            if isinstance(device, dict) and device.get("id")
        }

