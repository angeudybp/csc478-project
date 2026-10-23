"""preprocess: decode an uploaded image, strip its metadata, and resize it to 224x224."""
import base64
import io
import os
import warnings

from fastapi import Request
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from kb_common import ApiError, create_app

TARGET_SIZE = (224, 224)
ALLOWED_FORMATS = {"JPEG", "PNG"}

# Refuse decompression bombs: a tiny file that decodes to an enormous bitmap (risk R6).
Image.MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(40_000_000)))
warnings.simplefilter("error", Image.DecompressionBombWarning)

app = create_app("preprocess")


def preprocess_image(raw: bytes) -> dict:
    """Return the 224x224 model input as base64 JPEG plus the original dimensions."""
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        if fmt not in ALLOWED_FORMATS:
            raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", f"Unsupported image format: {fmt}")
        img.load()
        original_size = img.size
        # Apply the EXIF orientation before the metadata is dropped, so photos are not rotated.
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, TARGET_SIZE, Image.Resampling.BILINEAR)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=90)  # A fresh save carries no EXIF.
    except ApiError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Image dimensions are too large")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Not a valid JPEG or PNG image")

    return {
        "data": base64.b64encode(out.getvalue()).decode("ascii"),
        "width": TARGET_SIZE[0],
        "height": TARGET_SIZE[1],
        "originalWidth": original_size[0],
        "originalHeight": original_size[1],
        "originalFormat": fmt,
    }


@app.post("/preprocess")
async def preprocess(request: Request):
    raw = await request.body()
    if not raw:
        raise ApiError(400, "EMPTY_UPLOAD", "Request body is empty")
    # Decoding is CPU-bound; keep it off the event loop so health checks stay responsive.
    return await run_in_threadpool(preprocess_image, raw)
