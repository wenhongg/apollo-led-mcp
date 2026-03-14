"""FastAPI app — ties together WLED client, renderer, and web UI."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, field_validator

from src import config
from src.animations import EFFECTS, generate_gif, video_to_gif
from src.renderer import image_to_png, new_image, render_text
from src.wled import WLEDClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- State ---

wled: WLEDClient | None = None
current_mode: str = "off"
current_image: bytes | None = None  # cached PNG for preview

# Cached blank PNG (generated once)
_blank_png: bytes = image_to_png(new_image())

WLED_DISPLAY_FILENAME = "display.gif"  # single fixed name, always overwritten
ALLOWED_IMAGE_TYPES = {"image/gif", "image/png", "image/bmp"}
ALLOWED_VIDEO_TYPES = set(config.VIDEO_FORMATS.values())


# --- Helpers ---


def _get_wled() -> WLEDClient:
    if wled is None:
        raise HTTPException(status_code=503, detail="WLED device not configured. Set WLED_HOST in .env")
    return wled


async def _push_to_wled(data: bytes, mode: str, preview: Image.Image | None = None) -> None:
    """Upload GIF data to WLED and activate the Image effect. Updates local state."""
    global current_mode, current_image
    client = _get_wled()
    try:
        await client.upload_file(WLED_DISPLAY_FILENAME, data)
        await client.set_image_effect(WLED_DISPLAY_FILENAME)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Panel offline — cannot reach WLED at {config.WLED_HOST}: {type(e).__name__}")
    current_image = image_to_png(preview) if preview else None
    current_mode = mode


# --- Lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    global wled
    if config.WLED_HOST:
        wled = WLEDClient(config.WLED_HOST)
        logger.info("Connected to WLED at %s", config.WLED_HOST)
    else:
        logger.warning("WLED_HOST not set in .env")

    yield

    if wled:
        await wled.close()


app = FastAPI(title="Apollo LED Control", lifespan=lifespan)


# --- API ---


class _RGBValidatorMixin:
    @field_validator("color", "bg_color")
    @classmethod
    def validate_rgb(cls, v: tuple[int, int, int]) -> tuple[int, int, int]:
        if not all(0 <= c <= 255 for c in v):
            raise ValueError("RGB values must be 0-255")
        return v


class TextRequest(_RGBValidatorMixin, BaseModel):
    text: str = Field(max_length=200)
    color: tuple[int, int, int] = (255, 255, 255)
    bg_color: tuple[int, int, int] = (0, 0, 0)
    font_size: int = Field(default=12, ge=6, le=24)


class AnimatedTextRequest(_RGBValidatorMixin, BaseModel):
    text: str = Field(max_length=200)
    effect: str = Field(max_length=30)
    color: tuple[int, int, int] = (255, 255, 255)
    bg_color: tuple[int, int, int] = (0, 0, 0)
    font_size: int = Field(default=12, ge=6, le=24)
    speed: int = Field(default=100, ge=20, le=1000)
    num_frames: int | None = Field(default=None, ge=2, le=120)


class BrightnessRequest(BaseModel):
    brightness: int = Field(ge=0, le=255)


@app.post("/api/display/text")
async def display_text(req: TextRequest):
    img = await asyncio.to_thread(render_text, req.text, color=req.color, bg_color=req.bg_color, font_size=req.font_size)
    gif_bytes = await asyncio.to_thread(generate_gif, [img])
    await _push_to_wled(gif_bytes, "text", preview=img)
    return {"status": "ok", "mode": "text"}


@app.post("/api/display/animated-text")
async def display_animated_text(req: AnimatedTextRequest):
    if req.effect not in EFFECTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown effect '{req.effect}'. Available: {list(EFFECTS.keys())}",
        )

    effect_fn = EFFECTS[req.effect]
    kwargs = {
        "text": req.text,
        "color": req.color,
        "bg_color": req.bg_color,
        "font_size": req.font_size,
    }
    if req.num_frames is not None:
        kwargs["num_frames"] = req.num_frames

    frames = await asyncio.to_thread(effect_fn, **kwargs)
    gif_bytes = await asyncio.to_thread(generate_gif, frames, req.speed)

    if len(gif_bytes) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"Generated GIF too large ({len(gif_bytes)} bytes, max {config.MAX_UPLOAD_SIZE})")

    await _push_to_wled(gif_bytes, "animated-text", preview=frames[0])

    return {
        "status": "ok",
        "mode": "animated-text",
        "effect": req.effect,
        "frames": len(frames),
    }


@app.post("/api/display/gif")
async def display_gif(file: UploadFile):
    """Upload a GIF to WLED's filesystem and activate the native Image effect.

    The GIF persists and loops on the ESP32 — no need for Apollo to keep running.
    """
    if not file.content_type or not file.content_type.startswith("image/gif"):
        raise HTTPException(status_code=400, detail="File must be a GIF image")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large (max {config.MAX_UPLOAD_SIZE // 1024} KB)")
    await _push_to_wled(data, "gif")
    return {"status": "ok", "mode": "gif", "filename": WLED_DISPLAY_FILENAME}


@app.post("/api/display/image")
async def display_image(file: UploadFile):
    """Upload a still image (PNG/BMP/GIF) to WLED and display it via the native Image effect."""
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="File must be PNG, BMP, or GIF")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large (max {config.MAX_UPLOAD_SIZE // 1024} KB)")
    await _push_to_wled(data, "image")
    return {"status": "ok", "mode": "image", "filename": WLED_DISPLAY_FILENAME}


@app.post("/api/display/video")
async def display_video(
    file: UploadFile,
    fps: int = 10,
    max_duration: float = 10.0,
):
    """Convert a video (MP4/WEBM/MOV/AVI) to a 64x64 GIF and display on the panel."""
    if not file.content_type or file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="File must be a video (MP4, WEBM, MOV, AVI)")
    fps = max(1, min(30, fps))
    max_duration = max(0.5, min(30.0, max_duration))

    data = await file.read()
    if len(data) > config.MAX_VIDEO_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Video too large (max {config.MAX_VIDEO_UPLOAD // (1024 * 1024)} MB)")

    gif_bytes, frame_count = await asyncio.to_thread(video_to_gif, data, fps, max_duration)

    if len(gif_bytes) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Converted GIF too large ({len(gif_bytes)} bytes, max {config.MAX_UPLOAD_SIZE}). Try lower fps or shorter max_duration.",
        )

    await _push_to_wled(gif_bytes, "video")
    return {"status": "ok", "mode": "video", "frames": frame_count, "gif_size": len(gif_bytes)}


@app.post("/api/display/off")
async def display_off():
    global current_mode, current_image
    client = _get_wled()
    await client.turn_off()
    current_image = _blank_png
    current_mode = "off"
    return {"status": "ok", "mode": "off"}


@app.post("/api/brightness")
async def set_brightness(req: BrightnessRequest):
    client = _get_wled()
    await client.set_brightness(req.brightness)
    return {"status": "ok", "brightness": req.brightness}


@app.get("/api/status")
async def get_status():
    state = None
    if wled:
        try:
            state = await wled.get_state()
        except Exception:
            pass
    return {
        "mode": current_mode,
        "connected": wled is not None,
        "wled_host": config.WLED_HOST,
        "available_modes": ["text", "animated-text", "gif", "image", "video"],
        "wled_state": state,
    }


@app.get("/api/preview")
async def get_preview():
    content = current_image if current_image is not None else _blank_png
    return Response(content=content, media_type="image/png")


# --- Static files ---

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
