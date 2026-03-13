"""Animated text effects and video conversion for the LED panel."""

import colorsys
import io
import tempfile

from collections.abc import Callable

import imageio.v3 as iio
from PIL import Image, ImageDraw, ImageFont

from src.config import PANEL_HEIGHT, PANEL_WIDTH
from src.renderer import _load_font, new_image, render_text


def _measure_text(
    text: str, font_size: int
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, int, int]:
    """Load font and measure text dimensions. Returns (font, width, height)."""
    font = _load_font(font_size)
    bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


def _sliding_frames(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    pos_fn: Callable[[float], tuple[int, int]],
    num_frames: int,
    color: tuple[int, int, int],
    bg_color: tuple[int, int, int],
) -> list[Image.Image]:
    """Generate frames by sliding text across positions defined by pos_fn(t) for t in [0, 1]."""
    frames = []
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)
        x, y = pos_fn(t)
        img = new_image(bg_color)
        ImageDraw.Draw(img).text((x, y), text, fill=color, font=font)
        frames.append(img)
    return frames


def generate_gif(frames: list[Image.Image], frame_duration_ms: int = 100) -> bytes:
    """Assemble PIL frames into an animated GIF."""
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
    )
    return buf.getvalue()


def scroll_horizontal(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 64,
) -> list[Image.Image]:
    """Scroll text from right to left across the panel."""
    font, tw, th = _measure_text(text, font_size)
    cy = max(0, (PANEL_HEIGHT - th) // 2)
    return _sliding_frames(
        text, font,
        lambda t: (int(PANEL_WIDTH + (-tw - PANEL_WIDTH) * t), cy),
        num_frames, color, bg_color,
    )


def scroll_vertical(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 64,
) -> list[Image.Image]:
    """Scroll text from bottom to top across the panel."""
    font, tw, th = _measure_text(text, font_size)
    cx = max(0, (PANEL_WIDTH - tw) // 2)
    return _sliding_frames(
        text, font,
        lambda t: (cx, int(PANEL_HEIGHT + (-th - PANEL_HEIGHT) * t)),
        num_frames, color, bg_color,
    )


def flash(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 6,
) -> list[Image.Image]:
    """Alternate between text and blank frames."""
    text_img = render_text(text, color=color, bg_color=bg_color, font_size=font_size)
    blank_img = new_image(bg_color)
    return [text_img if i % 2 == 0 else blank_img for i in range(num_frames)]


def fade(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 20,
) -> list[Image.Image]:
    """Fade text in and out using a triangle wave."""
    font, tw, th = _measure_text(text, font_size)
    cx = max(0, (PANEL_WIDTH - tw) // 2)
    cy = max(0, (PANEL_HEIGHT - th) // 2)
    frames = []
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)
        alpha = 1.0 - 2.0 * abs(t - 0.5)
        blended = tuple(int(bg_color[c] + (color[c] - bg_color[c]) * alpha) for c in range(3))
        img = new_image(bg_color)
        ImageDraw.Draw(img).text((cx, cy), text, fill=blended, font=font)
        frames.append(img)
    return frames


def bounce(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 40,
) -> list[Image.Image]:
    """Bounce text horizontally using a triangle wave."""
    font, tw, th = _measure_text(text, font_size)
    cy = max(0, (PANEL_HEIGHT - th) // 2)
    max_offset = max(0, PANEL_WIDTH - tw)
    return _sliding_frames(
        text, font,
        lambda t: (int(max_offset * (1.0 - 2.0 * abs(t - 0.5))), cy),
        num_frames, color, bg_color,
    )


def typewriter(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int | None = None,
) -> list[Image.Image]:
    """Reveal text one character at a time."""
    hold = 4  # extra frames showing full text at the end
    if num_frames is None:
        num_frames = min(len(text) + hold, 120)
    frames = []
    chars_to_show = max(1, num_frames - hold)
    for i in range(num_frames):
        # Map frame index to number of characters
        if i < chars_to_show:
            n = int((i + 1) / chars_to_show * len(text))
            n = max(1, min(n, len(text)))
        else:
            n = len(text)
        partial = text[:n]
        img = render_text(partial, color=color, bg_color=bg_color, font_size=font_size)
        frames.append(img)
    return frames


def rainbow(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
    num_frames: int = 30,
) -> list[Image.Image]:
    """Cycle text color through the rainbow (ignores the color parameter)."""
    font, tw, th = _measure_text(text, font_size)
    cx = max(0, (PANEL_WIDTH - tw) // 2)
    cy = max(0, (PANEL_HEIGHT - th) // 2)
    frames = []
    for i in range(num_frames):
        hue = i / num_frames
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        img = new_image(bg_color)
        ImageDraw.Draw(img).text((cx, cy), text, fill=rgb, font=font)
        frames.append(img)
    return frames


def video_to_gif(
    video_data: bytes,
    fps: int = 10,
    max_duration: float = 10.0,
) -> tuple[bytes, int]:
    """Convert video bytes to a 64x64 GIF. Returns (gif_bytes, frame_count).

    Writes video to a temp file because imageio-ffmpeg needs a seekable path.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        tmp.write(video_data)
        tmp.flush()

        # Read metadata to determine duration and fps
        meta = iio.immeta(tmp.name, plugin="pyav")
        duration = min(meta.get("duration", max_duration), max_duration)
        source_fps = meta.get("fps", 30)
        step = max(1, round(source_fps / fps))
        max_frames = int(duration * fps)

        # Stream frames one at a time to avoid loading entire video into memory
        frames: list[Image.Image] = []
        for idx, frame in enumerate(iio.imiter(tmp.name, plugin="pyav")):
            if len(frames) >= max_frames:
                break
            if idx % step != 0:
                continue
            pil_img = Image.fromarray(frame)
            pil_img = pil_img.resize((PANEL_WIDTH, PANEL_HEIGHT), Image.LANCZOS)
            frames.append(pil_img)

    if not frames:
        raise ValueError("No frames extracted from video")

    frame_duration_ms = max(20, 1000 // fps)
    gif_bytes = generate_gif(frames, frame_duration_ms)
    return gif_bytes, len(frames)


EFFECTS: dict[str, Callable] = {
    "scroll_horizontal": scroll_horizontal,
    "scroll_vertical": scroll_vertical,
    "flash": flash,
    "fade": fade,
    "bounce": bounce,
    "typewriter": typewriter,
    "rainbow": rainbow,
}
