# Build from services-src/:  docker build -f inference/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY inference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kb_common.py inference/inference.py ./
RUN useradd --uid 10001 --no-create-home app && mkdir -p /var/log/app && chown 10001 /var/log/app
USER 10001
EXPOSE 8082
CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "8082", "--no-access-log"]
