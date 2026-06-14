FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

ARG CODEX_INSTALL_COMMAND="npm install -g @openai/codex"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        kaggle>=1.6.0 \
        numpy \
        pandas \
        scikit-learn \
        scipy \
        matplotlib \
        seaborn \
        joblib

RUN sh -lc "$CODEX_INSTALL_COMMAND"

WORKDIR /workspace

CMD ["codex", "--version"]
