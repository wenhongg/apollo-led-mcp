"""Render 64x64 images for the LED panel using Pillow."""

import io
import functools

from PIL import Image, ImageDraw, ImageFont

from src.config import PANEL_HEIGHT, PANEL_WIDTH

# Hard cap for decompression bomb protection — anything beyond this is absurd for a 64x64 panel
Image.MAX_IMAGE_PIXELS = 8_000 * 8_000

MAX_GIF_FRAMES = 200


@functools.lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bitmap-friendly font. Falls back to Pillow's default."""
    for name in [
        # CJK support (macOS / Linux)
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        # Latin fallbacks
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.dfont",
        "/System/Library/Fonts/Courier.dfont",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def new_image(bg_color: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    """Create a blank 64x64 RGB image."""
    return Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), bg_color)


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    """Draw text horizontally centered on the panel."""
    bbox = draw.textbbox((0, 0), text, font=font)
    x = max(0, (PANEL_WIDTH - bbox[2]) // 2)
    draw.text((x, y), text, fill=fill, font=font)


def render_text(
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 12,
) -> Image.Image:
    """Render text onto a 64x64 image, wrapping lines as needed."""
    img = new_image(bg_color)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    # Word-wrap with CJK support (CJK characters can break anywhere)
    lines: list[str] = []
    current_line = ""
    for char in text:
        if char == "\n":
            lines.append(current_line)
            current_line = ""
            continue
        test = current_line + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > PANEL_WIDTH - 2 and current_line:
            # For Latin text, try to break at last space
            if char != " " and " " in current_line:
                last_space = current_line.rfind(" ")
                lines.append(current_line[:last_space])
                current_line = current_line[last_space + 1:] + char
            else:
                lines.append(current_line)
                current_line = char.lstrip(" ")
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    # Center vertically
    line_height = draw.textbbox((0, 0), "Ay", font=font)[3] + 2
    total_height = line_height * len(lines)
    y = max(0, (PANEL_HEIGHT - total_height) // 2)

    for line in lines:
        draw_centered_text(draw, y, line, font, color)
        y += line_height

    return img


def resize_gif(data: bytes) -> bytes:
    """Resize an animated GIF to panel dimensions, preserving per-frame timing."""
    try:
        src = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Invalid GIF data: {exc}") from exc

    default_duration = src.info.get("duration", 100)
    n_frames = getattr(src, "n_frames", 1)
    step = max(1, n_frames // MAX_GIF_FRAMES)

    frames: list[Image.Image] = []
    durations: list[int] = []
    try:
        for i in range(0, n_frames, step):
            src.seek(i)
            durations.append(src.info.get("duration", default_duration))
            frame = src.copy().convert("RGB")
            frame = frame.resize((PANEL_WIDTH, PANEL_HEIGHT), Image.LANCZOS)
            frames.append(frame)
    except EOFError:
        pass

    if not frames:
        raise ValueError("GIF contains no frames")

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    return buf.getvalue()


def resize_image(data: bytes) -> bytes:
    """Resize a still image to panel dimensions and return as single-frame GIF."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Invalid image data: {exc}") from exc
    img = img.resize((PANEL_WIDTH, PANEL_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


def image_to_png(img: Image.Image) -> bytes:
    """Convert a Pillow Image to PNG bytes for preview."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
