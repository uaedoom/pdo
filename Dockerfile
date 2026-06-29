# Minimal container image for PDO.
#
#   docker build -t pdo .
#   docker run -it --rm -e OPENAI_API_KEY=sk-... -v "$PWD":/work -w /work pdo
#
# Mount your working directory at /work so PDO can read/write your files, and
# pass provider config via -e (OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL …).
FROM python:3.12-slim

# Git is handy because PDO ships a git tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

# Keep PDO's data/logs out of the read-only package dir.
ENV PDO_HOME=/root/.pdo
WORKDIR /work
ENTRYPOINT ["pdo"]
