FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/universe/attachments /var/lib/universe/faq-index /var/lib/universe/faq-models

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
