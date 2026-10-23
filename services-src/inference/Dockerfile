# Build from services-src/:  docker build -f inference/Dockerfile .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY inference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# MobileNetV2 (ImageNet-1k) from the ONNX Model Zoo, about 14 MB, built into the image so pods
# start without downloading anything. The build fails if the file does not match the checksum.
# The folder is created first: ADD --chmod would otherwise apply 644 to it too, making it unreadable.
RUN mkdir -m 755 model
ADD --checksum=sha256:c0c3f76d93fa3fd6580652a45618618a220fced18babf65774ed169de0432ad5 --chmod=644 \
    https://media.githubusercontent.com/media/onnx/models/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx \
    model/mobilenetv2-12.onnx
COPY inference/imagenet_classes.txt model/
COPY common/kb_common.py inference/inference.py ./
RUN useradd --uid 10001 --no-create-home app && mkdir -p /var/log/app && chown 10001 /var/log/app
USER 10001
EXPOSE 8082
CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "8082", "--no-access-log"]
