"""Render 64x64 images for the LED panel using Pillow."""

import io
import functools

from PIL import Image, ImageDraw, ImageFont

from src.config import PANEL_HEIGHT, PANEL_WIDTH


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


def image_to_png(img: Image.Image) -> bytes:
    """Convert a Pillow Image to PNG bytes for preview."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
