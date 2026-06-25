"""Data coordinator for Sensibo Custom."""

from __future__ import annotations

import asyncio
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
            device_map = {
                str(device["id"]): device
                for device in devices
                if isinstance(device, dict) and device.get("id")
            }
            details = await asyncio.gather(
                *(
                    self.client.async_get_device(pod_id)
                    for pod_id in device_map
                ),
                return_exceptions=True,
            )
        except SensiboAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (SensiboApiError, SensiboConnectionError) as err:
            raise UpdateFailed(str(err)) from err

        for pod_id, detail in zip(device_map, details, strict=False):
            if isinstance(detail, Exception):
                _LOGGER.debug("Failed to refresh Sensibo pod %s details: %s", pod_id, detail)
                continue
            if isinstance(detail, dict) and detail:
                device_map[pod_id] = {**device_map[pod_id], **detail}

        return device_map
