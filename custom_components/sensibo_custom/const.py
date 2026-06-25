"""Constants for the Sensibo Custom integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "sensibo_custom"

AUTH_METHOD = "auth_method"
AUTH_METHOD_ACCOUNT = "account"
AUTH_METHOD_API_KEY = "api_key"

CONF_BASE_URL = "base_url"
DEFAULT_BASE_URL = "https://home.sensibo.com"

DEFAULT_SCAN_INTERVAL_SECONDS = 60

PLATFORMS = [Platform.CLIMATE]

DEVICE_FIELDS = (
    "id,room,acState,connectionStatus,productModel,remoteCapabilities,"
    "location,features,measurements,mainMeasurementsSensor"
)

