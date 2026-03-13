import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WLED_HOST: str | None = os.getenv("WLED_HOST")
PANEL_WIDTH = 64
PANEL_HEIGHT = 64

MAX_UPLOAD_SIZE = 1 * 1024 * 1024       # 1 MB — LittleFS constraint
MAX_VIDEO_UPLOAD = 50 * 1024 * 1024     # 50 MB raw video limit

VIDEO_FORMATS = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
}
