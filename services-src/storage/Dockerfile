# Build from services-src/:  docker build -f storage/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY storage/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kv_common.py storage/storage.py ./
RUN useradd --uid 10001 --no-create-home app && mkdir /data && chown 10001 /data
USER 10001
EXPOSE 8083
CMD ["uvicorn", "storage:app", "--host", "0.0.0.0", "--port", "8083", "--no-access-log"]
