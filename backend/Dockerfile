FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Normalise line endings and set the exec bit. Without the CRLF strip, a
# checkout made on Windows produces `exec /app/docker-entrypoint.sh: no such
# file or directory` — the kernel reads the shebang as "/bin/sh\r" and looks
# for an interpreter of that exact name. The message names the script, not the
# interpreter, which makes it read like a missing file.
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# Runs migrations, then uvicorn. See docker-entrypoint.sh.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
