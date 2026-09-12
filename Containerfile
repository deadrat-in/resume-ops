FROM python:3.14-slim

ARG NPM_THEMES="jsonresume-theme-folio jsonresume-theme-stackoverflow"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Use system Chromium instead of bundled puppeteer Chromium (smaller image, no sandbox issues)
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV NODE_PATH=/data/themes/node_modules:/usr/local/lib/node_modules

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates nodejs npm \
        # Chromium and its runtime deps for PDF rendering via puppeteer
        chromium chromium-sandbox \
        # Fonts for resume rendering
        fonts-liberation fonts-noto-color-emoji \
    && npm install -g resumed puppeteer ${NPM_THEMES} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data /data/themes \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["python", "-m", "resume_ops_api"]

