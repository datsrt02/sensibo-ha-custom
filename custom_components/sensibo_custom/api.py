"""Async client for the Sensibo cloud API observed in the Android app."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import json
import logging
from typing import Any
from urllib.parse import quote

from aiohttp import ClientConnectionError, ClientResponseError, ClientSession

from .const import DEVICE_FIELDS

_LOGGER = logging.getLogger(__name__)


class SensiboError(Exception):
    """Base Sensibo client error."""


class SensiboAuthError(SensiboError):
    """Raised when Sensibo rejects credentials or the session."""


class SensiboConnectionError(SensiboError):
    """Raised when Sensibo cannot be reached."""


class SensiboApiError(SensiboError):
    """Raised when Sensibo returns an API-level error."""


class SensiboClient:
    """Minimal Sensibo API client.

    The APK uses cookie-backed account login through ``/api/v1/sessions`` and
    cloud device control through ``/api/v2/pods/{id}/acStates/{property}``.
    Public API keys are also supported; the app contains both an API key screen
    and the ``X-API-KEY`` header string.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str,
        api_key: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._email = email
        self._password = password
        self._logged_in = False
        self._cookies: dict[str, str] = {}

    async def async_login(self) -> None:
        """Create a cookie-backed account session."""
        if not self._email or not self._password:
            raise SensiboAuthError("Email and password are required for account login")

        payloads = (
            {"email": self._email, "password": self._password},
            {"user": {"email": self._email, "password": self._password}},
        )
        last_error: str | None = None

        for payload in payloads:
            status, data, text = await self._raw_request(
                "POST",
                "/api/v1/sessions",
                payload=payload,
                include_auth=False,
            )
            if 200 <= status < 300 and not self._is_failure_payload(data):
                self._logged_in = True
                return

            last_error = self._error_message(status, data, text)

        raise SensiboAuthError(last_error or "Unable to log in to Sensibo")

    async def async_get_user(self) -> dict[str, Any]:
        """Return the current Sensibo user."""
        result = await self._request("GET", "/api/v1/users/me")
        return result if isinstance(result, dict) else {}

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return all pods visible to the current account."""
        result = await self._request(
            "GET",
            "/api/v2/users/me/pods",
            params={"fields": DEVICE_FIELDS},
        )
        return self._coerce_device_list(result)

    async def async_get_device(self, pod_id: str) -> dict[str, Any]:
        """Return a single pod."""
        result = await self._request(
            "GET",
            f"/api/v2/pods/{quote(pod_id, safe='')}",
            params={"fields": DEVICE_FIELDS},
        )
        return result if isinstance(result, dict) else {}

    async def async_set_ac_state_property(
        self, pod_id: str, property_name: str, value: Any
    ) -> Any:
        """Set one AC state property on a pod."""
        return await self._request(
            "PATCH",
            (
                f"/api/v2/pods/{quote(pod_id, safe='')}/acStates/"
                f"{quote(property_name, safe='')}"
            ),
            payload={"newValue": value},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        include_auth: bool = True,
        retry_auth: bool = True,
    ) -> Any:
        """Run a request and unwrap Sensibo's ``result`` envelope."""
        if include_auth and not self._api_key and not self._logged_in:
            await self.async_login()

        status, data, text = await self._raw_request(
            method,
            path,
            params=params,
            payload=payload,
            include_auth=include_auth,
        )

        if status in (401, 403) and include_auth and retry_auth and not self._api_key:
            self._logged_in = False
            await self.async_login()
            return await self._request(
                method,
                path,
                params=params,
                payload=payload,
                include_auth=include_auth,
                retry_auth=False,
            )

        if status in (401, 403):
            raise SensiboAuthError(self._error_message(status, data, text))

        if status < 200 or status >= 300:
            raise SensiboApiError(self._error_message(status, data, text))

        if self._is_failure_payload(data):
            raise SensiboApiError(self._error_message(status, data, text))

        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        include_auth: bool = True,
    ) -> tuple[int, Any, str]:
        """Run a raw HTTP request."""
        request_params = dict(params or {})
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-SensiboCustom/0.1",
        }

        if include_auth and self._api_key:
            request_params.setdefault("apiKey", self._api_key)
            headers["X-API-KEY"] = self._api_key
        elif include_auth and self._cookies:
            headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in self._cookies.items()
            )

        try:
            async with asyncio.timeout(30):
                response = await self._session.request(
                    method,
                    f"{self._base_url}{path}",
                    params=request_params,
                    json=payload,
                    headers=headers,
                )
                async with response:
                    text = await response.text()
                    self._store_response_cookies(response)
                    data = self._parse_json(text)
                    return response.status, data, text
        except (ClientConnectionError, ClientResponseError, TimeoutError) as err:
            raise SensiboConnectionError("Unable to connect to Sensibo") from err

    @staticmethod
    def _parse_json(text: str) -> Any:
        """Parse JSON, returning raw text for non-JSON responses."""
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    def _store_response_cookies(self, response: Any) -> None:
        """Store response cookies for account-authenticated requests."""
        for name, morsel in response.cookies.items():
            self._cookies[name] = morsel.value

    @staticmethod
    def _is_failure_payload(data: Any) -> bool:
        """Return true when Sensibo's envelope represents an error."""
        return isinstance(data, dict) and data.get("status") in {
            "failure",
            "fail",
            "error",
        }

    @staticmethod
    def _coerce_device_list(result: Any) -> list[dict[str, Any]]:
        """Normalize different Sensibo list envelopes."""
        if isinstance(result, list):
            return [device for device in result if isinstance(device, dict)]
        if isinstance(result, dict):
            for key in ("pods", "devices", "items"):
                value = result.get(key)
                if isinstance(value, list):
                    return [device for device in value if isinstance(device, dict)]
        return []

    @staticmethod
    def _error_message(status: int, data: Any, text: str) -> str:
        """Build a useful API error message without leaking large payloads."""
        if isinstance(data, dict):
            for key in ("message", "error", "reason"):
                value = data.get(key)
                if value:
                    return f"Sensibo API returned {status}: {value}"
            if data.get("status"):
                return f"Sensibo API returned {status}: {data.get('status')}"
        if text:
            return f"Sensibo API returned {status}: {text[:200]}"
        return f"Sensibo API returned {status}"
