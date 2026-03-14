"""WLED client — HTTP JSON API for brightness, on/off, and image effects."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class WLEDClient:
    def __init__(self, host: str):
        self.host = host
        self._http = httpx.AsyncClient(base_url=f"http://{host}", timeout=2.0)
        self._image_fx_id: int | None = None

    async def _request(self, method: str, path: str, retries: int = 2, **kwargs) -> httpx.Response:
        """Send an HTTP request with retry on connection errors (ESP32 may be busy after flash writes)."""
        for attempt in range(retries):
            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = 2.0
                resp = await self._http.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
                if attempt == retries - 1:
                    raise
                delay = 0.2
                logger.warning("WLED connection failed (attempt %d/%d), retrying in %.1fs", attempt + 1, retries, delay)
                await asyncio.sleep(delay)

    async def _post_state(self, payload: dict) -> dict:
        resp = await self._request("POST", "/json/state", json=payload)
        return resp.json()

    async def _get_json(self, path: str) -> dict:
        resp = await self._request("GET", path)
        return resp.json()

    async def set_brightness(self, brightness: int) -> dict:
        return await self._post_state({"bri": max(0, min(255, brightness))})

    async def turn_off(self) -> dict:
        return await self._post_state({"on": False})

    async def get_state(self) -> dict:
        return await self._get_json("/json/state")

    async def upload_file(self, filename: str, data: bytes) -> None:
        """Upload a file to WLED's LittleFS via /edit."""
        await self._request(
            "POST", "/edit",
            files={"data": (f"/{filename}", data)},
            timeout=30.0,
        )

    async def get_effects(self) -> list[str]:
        """Get list of effect names from WLED."""
        return await self._get_json("/json/effects")

    async def set_image_effect(self, filename: str) -> dict:
        """Activate the Image effect displaying the given file."""
        if self._image_fx_id is None:
            effects = await self.get_effects()
            try:
                self._image_fx_id = effects.index("Image")
            except ValueError:
                raise RuntimeError(
                    "WLED firmware does not have the 'Image' effect. "
                    "Ensure you are running WLED-MM or a build with Image support."
                )
        # Toggle to solid black first to force WLED to reload the file from LittleFS
        await self._post_state({"seg": [{"id": 0, "fx": 0, "col": [[0, 0, 0]]}]})
        await asyncio.sleep(0.5)
        return await self._post_state({
            "on": True,
            "seg": [{"id": 0, "fx": self._image_fx_id, "n": filename}]
        })

    async def close(self) -> None:
        await self._http.aclose()
