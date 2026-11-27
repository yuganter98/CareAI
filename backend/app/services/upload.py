import hashlib
import logging
import os
import uuid
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

# Extensions the extraction pipeline can actually read → canonical file_type.
ALLOWED_EXTENSIONS = {
    "pdf": "pdf",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
}

# Magic-byte signatures so a renamed .exe can't pass as a PDF.
_SIGNATURES = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}

_CHUNK_SIZE = 1024 * 1024  # 1MB


def detect_file_type(filename: str | None) -> tuple[str, str]:
    """
    Return (extension, canonical_file_type) for an uploaded filename.
    Raises 415 when the extension is not one the pipeline supports.
    """
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '.{ext or '?'}'. Allowed: {allowed}.",
        )
    return ext, ALLOWED_EXTENSIONS[ext]


async def save_upload_file(upload_file: UploadFile) -> tuple[str, str]:
    """
    Validate and persist an uploaded report. Returns (path, sha256).

    - extension must be in ALLOWED_EXTENSIONS
    - content must start with the matching file signature
    - size must not exceed MAX_UPLOAD_SIZE_MB
    The stored name is a random hex id, so the client filename never reaches the path.

    The digest is taken over the bytes as they stream past, so detecting a
    re-upload costs no extra read of the file. It covers only the bytes
    actually written, which matters for the rejection paths: a file that blew
    the size limit is deleted and never gets a hash at all.
    """
    ext, _ = detect_file_type(upload_file.filename)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}.{ext}")

    written = 0
    digest = hashlib.sha256()
    try:
        with open(file_path, "wb") as buffer:
            first = True
            while True:
                chunk = await upload_file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if first:
                    if not chunk.startswith(_SIGNATURES[ext]):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"File content does not look like a valid .{ext} file.",
                        )
                    first = False
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,  # Payload Too Large
                        detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit.",
                    )
                digest.update(chunk)
                buffer.write(chunk)
        if written == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    except HTTPException:
        remove_stored_file(file_path)
        raise
    except Exception as e:
        remove_stored_file(file_path)
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # In future setups with S3, this would return an S3 URI. Currently, returning local path.
    return file_path, digest.hexdigest()


def remove_stored_file(file_path: str | None) -> None:
    """Best-effort delete of a stored upload; only touches files inside UPLOAD_DIR."""
    if not file_path:
        return
    upload_root = os.path.realpath(settings.UPLOAD_DIR)
    target = os.path.realpath(file_path)
    try:
        inside = os.path.commonpath([upload_root, target]) == upload_root
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        logger.warning("Refusing to delete file outside UPLOAD_DIR: %s", file_path)
        return
    try:
        os.remove(target)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not delete stored file %s: %s", file_path, e)
