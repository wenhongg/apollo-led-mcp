FROM python:3.13-slim

WORKDIR /app

# System deps for Pillow, PyAV, and a readable font
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libjpeg62-turbo libpng16-16 fonts-dejavu-core fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 9092

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9092"]
