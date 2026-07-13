"""Minimal SparkSync API client."""

from __future__ import annotations

from typing import Any

import aiohttp


class SparkSyncError(Exception):
    """Any API failure."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SparkSyncAuthError(SparkSyncError):
    """Bad credentials."""


class SparkSyncApi:
    """Thin async client for the SparkSync REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._access_token: str | None = None

    async def async_login(self) -> None:
        try:
            async with self._session.post(
                f"{self._base}/auth/login",
                json={"username": self._username, "password": self._password},
            ) as resp:
                if resp.status == 401:
                    raise SparkSyncAuthError("Invalid credentials", 401)
                if resp.status >= 400:
                    raise SparkSyncError(f"Login failed: HTTP {resp.status}", resp.status)
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise SparkSyncError(f"Cannot connect: {err}") from err
        self._access_token = data["access_token"]

    async def _request(self, method: str, path: str, *, retry: bool = True) -> Any:
        # ponytail: re-login on 401 instead of refresh-token rotation — creds are
        # stored anyway and rotation adds already-used/race failure modes.
        if self._access_token is None:
            await self.async_login()
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
            ) as resp:
                if resp.status == 401 and retry:
                    self._access_token = None
                    return await self._request(method, path, retry=False)
                if resp.status >= 400:
                    body = await resp.json(content_type=None)
                    message = (body or {}).get("message", f"HTTP {resp.status}")
                    raise SparkSyncError(message, resp.status)
                return await resp.json()
        except aiohttp.ClientError as err:
            raise SparkSyncError(f"Cannot connect: {err}") from err

    async def async_get_devices(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/devices")

    async def async_get_info(self, device_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/info?id={device_id}")
