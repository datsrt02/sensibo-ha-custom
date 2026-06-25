"""Climate entities for Sensibo Custom."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SensiboDataUpdateCoordinator

SENSIBO_TO_HA_MODE = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
    "fan_only": HVACMode.FAN_ONLY,
    "auto": HVACMode.HEAT_COOL,
}

HA_TO_SENSIBO_MODE = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan",
    HVACMode.HEAT_COOL: "auto",
}

DEFAULT_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
    HVACMode.HEAT_COOL,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sensibo climate entities."""
    coordinator: SensiboDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SensiboClimate(coordinator, pod_id)
        for pod_id, device in coordinator.data.items()
        if _looks_like_climate_device(device)
    )


def _looks_like_climate_device(device: dict[str, Any]) -> bool:
    """Return true when a Sensibo pod should be represented as climate."""
    return bool(device.get("acState") or device.get("remoteCapabilities"))


class SensiboClimate(CoordinatorEntity[SensiboDataUpdateCoordinator], ClimateEntity):
    """Sensibo climate entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SensiboDataUpdateCoordinator, pod_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._pod_id = pod_id
        device = self._device
        name = _room_name(device) or f"Sensibo {pod_id}"
        self._attr_unique_id = f"{DOMAIN}_{pod_id}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, pod_id)},
            "manufacturer": "Sensibo",
            "name": name,
            "model": device.get("productModel"),
        }

    @property
    def _device(self) -> dict[str, Any]:
        """Return the latest device payload."""
        return self.coordinator.data.get(self._pod_id, {})

    @property
    def _ac_state(self) -> dict[str, Any]:
        """Return the current AC state payload."""
        ac_state = self._device.get("acState")
        return ac_state if isinstance(ac_state, dict) else {}

    @property
    def _remote_capabilities(self) -> dict[str, Any]:
        """Return remote capabilities."""
        capabilities = self._device.get("remoteCapabilities")
        return capabilities if isinstance(capabilities, dict) else {}

    @property
    def available(self) -> bool:
        """Return whether the device is available."""
        if not super().available:
            return False

        status = self._device.get("connectionStatus")
        if isinstance(status, dict):
            for key in ("isAlive", "connected", "online"):
                if key in status:
                    return bool(status[key])
            status = status.get("status") or status.get("value")

        if isinstance(status, str):
            return status.lower() not in {"disconnected", "offline", "dead"}

        return True

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported climate features."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self.swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        features |= getattr(ClimateEntityFeature, "TURN_ON", ClimateEntityFeature(0))
        features |= getattr(ClimateEntityFeature, "TURN_OFF", ClimateEntityFeature(0))
        return features

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self._ac_state.get("on") is False or self._ac_state.get("isOn") is False:
            return HVACMode.OFF
        return SENSIBO_TO_HA_MODE.get(str(self._ac_state.get("mode")), HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return available HVAC modes."""
        modes = [HVACMode.OFF]
        raw_modes = self._capability_modes()
        for mode in raw_modes:
            ha_mode = SENSIBO_TO_HA_MODE.get(str(mode))
            if ha_mode and ha_mode not in modes:
                modes.append(ha_mode)
        return modes if len(modes) > 1 else DEFAULT_HVAC_MODES

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return _as_float(self._ac_state.get("targetTemperature"))

    @property
    def current_temperature(self) -> float | None:
        """Return measured temperature."""
        measurements = _measurements(self._device)
        return _as_float(measurements.get("temperature"))

    @property
    def current_humidity(self) -> int | None:
        """Return measured humidity."""
        measurements = _measurements(self._device)
        humidity = _as_float(measurements.get("humidity"))
        return round(humidity) if humidity is not None else None

    @property
    def temperature_unit(self) -> str:
        """Return the configured temperature unit."""
        unit = str(self._ac_state.get("temperatureUnit") or "").upper()
        if unit == "F":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self) -> float:
        """Return target temperature step."""
        values = self._temperature_values_for_current_mode()
        if len(values) >= 2:
            diffs = sorted(
                {
                    round(values[index + 1] - values[index], 2)
                    for index in range(len(values) - 1)
                    if values[index + 1] > values[index]
                }
            )
            if diffs:
                return diffs[0]
        return 1.0

    @property
    def min_temp(self) -> float:
        """Return minimum supported target temperature."""
        values = self._temperature_values_for_current_mode()
        if values:
            return min(values)
        return 60 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 16

    @property
    def max_temp(self) -> float:
        """Return maximum supported target temperature."""
        values = self._temperature_values_for_current_mode()
        if values:
            return max(values)
        return 90 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 30

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        value = self._ac_state.get("fanLevel")
        return str(value) if value is not None else None

    @property
    def fan_modes(self) -> list[str] | None:
        """Return supported fan modes."""
        values = self._capability_values_for_current_mode(
            "fanLevels",
            "fan_levels",
            "supportedFanLevels",
            "supported_fan_levels",
        )
        if not values and self.fan_mode:
            values = [self.fan_mode]
        return values or None

    @property
    def swing_mode(self) -> str | None:
        """Return current vertical swing mode."""
        value = self._ac_state.get("swing")
        return str(value) if value is not None else None

    @property
    def swing_modes(self) -> list[str] | None:
        """Return supported vertical swing modes."""
        values = self._capability_values_for_current_mode(
            "swing",
            "swings",
            "swingModes",
            "supportedSwing",
            "supported_swing_modes",
        )
        if not values and self.swing_mode:
            values = [self.swing_mode]
        return values or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        ac_state = self._ac_state
        return {
            "pod_id": self._pod_id,
            "product_model": self._device.get("productModel"),
            "connection_status": self._device.get("connectionStatus"),
            "horizontal_swing": ac_state.get("horizontalSwing"),
            "light": ac_state.get("light"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._set_ac_property("on", False)
            return

        sensibo_mode = HA_TO_SENSIBO_MODE[hvac_mode]
        if self.hvac_mode == HVACMode.OFF:
            await self._set_ac_property("on", True, refresh=False)
        if self._ac_state.get("mode") != sensibo_mode:
            await self._set_ac_property("mode", sensibo_mode, refresh=False)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the AC on."""
        await self._set_ac_property("on", True)

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self._set_ac_property("on", False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature and optional HVAC mode."""
        hvac_mode = kwargs.get("hvac_mode")
        if hvac_mode is not None and hvac_mode != self.hvac_mode:
            await self.async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._set_ac_property("targetTemperature", temperature)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        await self._set_ac_property("fanLevel", fan_mode)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set vertical swing mode."""
        await self._set_ac_property("swing", swing_mode)

    async def _set_ac_property(
        self, property_name: str, value: Any, *, refresh: bool = True
    ) -> None:
        """Set a Sensibo AC property."""
        await self.coordinator.client.async_set_ac_state_property(
            self._pod_id, property_name, value
        )
        if refresh:
            await self.coordinator.async_request_refresh()

    def _capability_modes(self) -> list[str]:
        """Return raw Sensibo mode names from capabilities."""
        modes = self._remote_capabilities.get("modes")
        if isinstance(modes, dict):
            return [str(mode) for mode in modes]
        if isinstance(modes, list):
            return [str(mode) for mode in modes]

        for key in ("supportedModes", "supported_modes"):
            values = _string_list(self._remote_capabilities.get(key))
            if values:
                return values

        return []

    def _capability_for_current_mode(self) -> dict[str, Any]:
        """Return capability payload for the active Sensibo mode."""
        mode = self._ac_state.get("mode")
        modes = self._remote_capabilities.get("modes")
        if isinstance(modes, dict) and mode in modes and isinstance(modes[mode], dict):
            return modes[mode]
        return self._remote_capabilities

    def _capability_values_for_current_mode(self, *keys: str) -> list[str]:
        """Read a string list from current mode capabilities."""
        capability = self._capability_for_current_mode()
        for key in keys:
            values = _string_list(capability.get(key))
            if values:
                return values
        return []

    def _temperature_values_for_current_mode(self) -> list[float]:
        """Return supported target temperature values for current mode."""
        capability = self._capability_for_current_mode()
        temperatures = capability.get("temperatures") or capability.get("temperature")
        unit = "F" if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else "C"

        candidates: list[Any] = []
        if isinstance(temperatures, dict):
            unit_payload = (
                temperatures.get(unit)
                or temperatures.get(unit.lower())
                or temperatures.get(self.temperature_unit)
                or temperatures
            )
            if isinstance(unit_payload, dict):
                candidates = (
                    unit_payload.get("values")
                    or unit_payload.get("range")
                    or unit_payload.get("temperatures")
                    or []
                )
            elif isinstance(unit_payload, list):
                candidates = unit_payload
        elif isinstance(temperatures, list):
            candidates = temperatures

        values = sorted(value for value in (_as_float(item) for item in candidates) if value)
        return values


def _room_name(device: dict[str, Any]) -> str | None:
    """Return a friendly room/device name."""
    room = device.get("room")
    if isinstance(room, str):
        return room
    if isinstance(room, dict):
        for key in ("name", "roomName"):
            if room.get(key):
                return str(room[key])
    if device.get("name"):
        return str(device["name"])
    return None


def _measurements(device: dict[str, Any]) -> dict[str, Any]:
    """Return measurement payload."""
    for key in ("measurements", "mainMeasurementsSensor"):
        value = device.get(key)
        if isinstance(value, dict):
            nested = value.get("measurements")
            if isinstance(nested, dict):
                return nested
            return value
    return {}


def _string_list(value: Any) -> list[str]:
    """Coerce a list-like capability value to strings."""
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        for key in ("values", "items", "options"):
            nested = _string_list(value.get(key))
            if nested:
                return nested
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [str(item) for item in value if item is not None]
    return []


def _as_float(value: Any) -> float | None:
    """Convert a value to float."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("value", "current", "temperature", "humidity"):
            result = _as_float(value.get(key))
            if result is not None:
                return result
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
