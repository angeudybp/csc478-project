# Build from services-src/:  docker build -f gateway/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kb_common.py gateway/gateway.py ./
COPY gateway/static/ ./static/
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8080
CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
