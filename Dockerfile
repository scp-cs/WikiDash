FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home wikidash
USER wikidash
WORKDIR /data

ENV WIKICOMMA_CONFIG=/data/config.json
ENTRYPOINT ["python", "-m", "wikidash"]
