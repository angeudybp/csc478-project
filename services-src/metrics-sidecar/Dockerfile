# Build from services-src/:  docker build -f metrics-sidecar/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY metrics-sidecar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kv_common.py metrics-sidecar/exporter.py ./
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 9100
CMD ["uvicorn", "exporter:app", "--host", "0.0.0.0", "--port", "9100", "--no-access-log"]
