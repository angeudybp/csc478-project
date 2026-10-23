# Build from services-src/:  docker build -f gateway/Dockerfile .

# Stage 1: compile the React UI. Node is only needed here, never in the running image.
FROM node:20.18-alpine AS ui
WORKDIR /ui
COPY gateway/ui/package.json gateway/ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY gateway/ui/ ./
RUN npm run build

# Stage 2: the gateway itself, serving the compiled UI from ./static.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/kb_common.py gateway/gateway.py ./
COPY --from=ui /ui/dist/ ./static/
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8080
CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
