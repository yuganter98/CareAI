import os
import uuid
from fastapi import UploadFile, HTTPException
from app.core.config import settings

async def save_upload_file(upload_file: UploadFile) -> str:
    # Ensure the 'uploads' directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    # Generate a unique file name to avoid collisions
    file_extension = upload_file.filename.split(".")[-1] if "." in upload_file.filename else ""
    unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
    
    try:
        # Read the file asynchronously in chunks to avoid blowing up memory with large files
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await upload_file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                buffer.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
        
    # In future setups with S3, this would return an S3 URI. Currently, returning local path.
    return file_path
