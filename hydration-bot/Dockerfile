# ---------- builder stage ----------
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies (none needed for our pure-Python wheels, but
# keeping the stage for future extensibility).
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- runtime stage ----------
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder.
COPY --from=builder /install /usr/local

# Application code.
COPY bot/ ./bot/
COPY requirements.txt .

# Run as non-root for security.
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import telegram; print('ok')" || exit 1

CMD ["python", "-m", "bot.main"]
