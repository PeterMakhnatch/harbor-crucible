FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl git jq procps ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash player
