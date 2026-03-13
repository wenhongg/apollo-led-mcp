# Apollo LED Control

Control an [Apollo Matrix M1](https://apolloautomation.com/products/m-1-led-matrix) (64x64 HUB75 LED panel running WLED-MM) via a web UI, REST API, or MCP tools for AI agents.

## Quick Start

```bash
cp .env.example .env   # edit WLED_HOST to match your panel IP
docker compose up -d
```

Open `http://localhost:9092` for the web UI.

### Without Docker

```bash
python -m venv venv && source venv/bin/activate
pip install .
uvicorn src.main:app --port 9092
```

## API

All display endpoints upload a GIF to the WLED filesystem and activate the native Image effect. Content persists on the panel across reboots without Apollo running.

### Display

| Method | Endpoint | Body / Params | Description |
|--------|----------|---------------|-------------|
| POST | `/api/display/text` | `{"text", "color", "bg_color", "font_size"}` | Static text |
| POST | `/api/display/animated-text` | `{"text", "effect", "color", "bg_color", "font_size", "speed", "num_frames"}` | Animated text |
| POST | `/api/display/gif` | multipart `file` | Upload and display a GIF |
| POST | `/api/display/image` | multipart `file` | Upload and display a still image (PNG/BMP/GIF) |
| POST | `/api/display/video` | multipart `file`, query `fps`, `max_duration` | Convert video to 64x64 GIF and display |
| POST | `/api/display/off` | — | Turn off the panel |

### Controls

| Method | Endpoint | Body / Params | Description |
|--------|----------|---------------|-------------|
| POST | `/api/brightness` | `{"brightness": 0-255}` | Set brightness |
| GET | `/api/status` | — | Panel status and connection info |
| GET | `/api/preview` | — | PNG preview of current display |

### Animated Text Effects

`scroll_horizontal`, `scroll_vertical`, `flash`, `fade`, `bounce`, `typewriter`, `rainbow`

### Examples

```bash
# Static text
curl -X POST http://localhost:9092/api/display/text \
  -H 'Content-Type: application/json' \
  -d '{"text": "hello", "color": [255, 255, 0]}'

# Scrolling text
curl -X POST http://localhost:9092/api/display/animated-text \
  -H 'Content-Type: application/json' \
  -d '{"text": "hello", "effect": "scroll_horizontal"}'

# Upload a GIF
curl -X POST http://localhost:9092/api/display/gif -F "file=@cat.gif"

# Convert and display a video
curl -X POST "http://localhost:9092/api/display/video?fps=10&max_duration=5" -F "file=@clip.mp4"
```

## MCP Server

Apollo exposes the same functionality as MCP tools for AI agents (e.g. Claude Code). The `.mcp.json` config is included — start the Apollo server and open a new Claude Code session in this directory.

Tools: `display_text`, `display_animated_text`, `display_gif`, `display_image`, `display_video`, `display_off`, `set_brightness`, `get_status`, `get_preview`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WLED_HOST` | — | WLED device IP or hostname (required) |
| `APOLLO_URL` | `http://localhost:9092` | Used by MCP server to reach Apollo |
