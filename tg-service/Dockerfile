FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY tg-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY tg_service ./tg_service

CMD ["uvicorn", "tg_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
