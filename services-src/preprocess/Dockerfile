# Build from services-src/:  docker build -f preprocess/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY preprocess/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kb_common.py preprocess/preprocess.py ./
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8081
CMD ["uvicorn", "preprocess:app", "--host", "0.0.0.0", "--port", "8081", "--no-access-log"]
