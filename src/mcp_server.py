"""MCP server — exposes Apollo LED panel API as tools for AI agents."""

import base64
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from src.config import MAX_UPLOAD_SIZE, MAX_VIDEO_UPLOAD, VIDEO_FORMATS

APOLLO_URL = os.environ.get("APOLLO_URL", "http://localhost:9092")
MAX_B64_LEN = 2 * 1024 * 1024  # ~1 MB decoded (base64 overhead ~33%)

_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    if _http is None:
        raise RuntimeError("HTTP client not initialized")
    return _http


@asynccontextmanager
async def _lifespan(_mcp: FastMCP):
    global _http
    _http = httpx.AsyncClient(base_url=APOLLO_URL, timeout=30)
    yield
    await _http.aclose()
    _http = None


mcp = FastMCP("apollo-led", lifespan=_lifespan)

_METHODS = {"get", "post"}


async def _call(method: str, path: str, **kwargs) -> str:
    """Make an HTTP request to Apollo and return the JSON response as a string."""
    if method not in _METHODS:
        raise ValueError(f"Unsupported HTTP method: {method}")
    client = _get_http()
    resp = await getattr(client, method)(path, **kwargs)
    resp.raise_for_status()
    return resp.text


def _resolve_file_input(
    file_path: str | None,
    base64_data: str | None,
    default_name: str,
    max_size: int = MAX_UPLOAD_SIZE,
) -> tuple[bytes, str]:
    """Resolve file_path or base64_data into (bytes, filename). Raises on error."""
    if file_path:
        resolved = Path(file_path).resolve()
        # Restrict to /tmp and user's home directory
        allowed = [Path("/tmp"), Path.home()]
        if not any(resolved.is_relative_to(d) for d in allowed):
            raise ValueError(f"File path must be under /tmp or home directory")
        size = os.path.getsize(resolved)
        if size > max_size:
            raise ValueError(f"File too large ({size} bytes, max {max_size})")
        with open(resolved, "rb") as f:
            data = f.read()
        return data, resolved.name
    elif base64_data:
        if len(base64_data) > MAX_B64_LEN:
            raise ValueError("Base64 data too large (max ~1 MB decoded)")
        try:
            data = base64.b64decode(base64_data, validate=True)
        except Exception:
            raise ValueError("Invalid base64 data")
        return data, default_name
    else:
        raise ValueError("Provide either file_path or base64_data")


@mcp.tool()
async def display_gif(file_path: str | None = None, base64_data: str | None = None) -> str:
    """Display an animated GIF on the LED panel. Uploads to WLED filesystem — persists without Apollo running.

    Provide either a local file path or base64-encoded GIF data.
    """
    data, filename = _resolve_file_input(file_path, base64_data, "image.gif")
    client = _get_http()
    resp = await client.post(
        "/api/display/gif",
        files={"file": (filename, data, "image/gif")},
    )
    resp.raise_for_status()
    return resp.text


@mcp.tool()
async def display_image(file_path: str | None = None, base64_data: str | None = None) -> str:
    """Display a still image (PNG/BMP/GIF) on the LED panel. Uploads to WLED filesystem — persists without Apollo running.

    Provide either a local file path or base64-encoded image data.
    """
    data, filename = _resolve_file_input(file_path, base64_data, "display.gif")
    client = _get_http()
    resp = await client.post(
        "/api/display/image",
        files={"file": (filename, data, "application/octet-stream")},
    )
    resp.raise_for_status()
    return resp.text


@mcp.tool()
async def display_text(
    text: str,
    color: list[int] | None = None,
    bg_color: list[int] | None = None,
    font_size: int = 12,
) -> str:
    """Display text on the LED panel. Color and bg_color are [R, G, B] (0-255)."""
    body: dict = {"text": text, "font_size": font_size}
    if color:
        body["color"] = color
    if bg_color:
        body["bg_color"] = bg_color
    return await _call("post", "/api/display/text", json=body)


@mcp.tool()
async def display_animated_text(
    text: str,
    effect: str,
    color: list[int] | None = None,
    bg_color: list[int] | None = None,
    font_size: int = 12,
    speed: int = 100,
    num_frames: int | None = None,
) -> str:
    """Display animated text on the LED panel.

    Effects: scroll_horizontal, scroll_vertical, flash, fade, bounce, typewriter, rainbow.
    Color and bg_color are [R, G, B] (0-255). Speed is ms per frame (20-1000).
    """
    body: dict = {"text": text, "effect": effect, "font_size": font_size, "speed": speed}
    if color:
        body["color"] = color
    if bg_color:
        body["bg_color"] = bg_color
    if num_frames is not None:
        body["num_frames"] = num_frames
    return await _call("post", "/api/display/animated-text", json=body)


@mcp.tool()
async def display_video(
    file_path: str | None = None,
    base64_data: str | None = None,
    fps: int = 10,
    max_duration: float = 10.0,
) -> str:
    """Convert a video (MP4/WEBM/MOV/AVI) to a 64x64 GIF and display on the LED panel.

    Provide either a local file path or base64-encoded video data.
    fps: target frames per second (1-30). max_duration: max seconds to convert (0.5-30).
    """
    data, filename = _resolve_file_input(file_path, base64_data, "video.mp4", max_size=MAX_VIDEO_UPLOAD)
    ext = os.path.splitext(filename)[1].lower()
    content_type = VIDEO_FORMATS.get(ext, "video/mp4")

    client = _get_http()
    resp = await client.post(
        "/api/display/video",
        files={"file": (filename, data, content_type)},
        params={"fps": fps, "max_duration": max_duration},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.text


@mcp.tool()
async def display_off() -> str:
    """Turn off the LED panel."""
    return await _call("post", "/api/display/off")


@mcp.tool()
async def set_brightness(brightness: int) -> str:
    """Set LED panel brightness (0-255)."""
    if not 0 <= brightness <= 255:
        return "Error: brightness must be 0-255"
    return await _call("post", "/api/brightness", json={"brightness": brightness})


@mcp.tool()
async def get_status() -> str:
    """Get the current status of the LED panel (mode, connection, available modes)."""
    return await _call("get", "/api/status")


@mcp.tool()
async def get_preview() -> str:
    """Get a PNG preview of what's currently displayed on the LED panel. Returns base64-encoded PNG."""
    client = _get_http()
    resp = await client.get("/api/preview")
    resp.raise_for_status()
    return "data:image/png;base64," + base64.b64encode(resp.content).decode()


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "sse":
        port = int(os.environ.get("MCP_SSE_PORT", "8001"))
        mcp.run(transport="sse", port=port)
    else:
        mcp.run()
