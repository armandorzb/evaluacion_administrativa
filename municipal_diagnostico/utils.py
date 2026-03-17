from __future__ import annotations

from pathlib import Path
import uuid

from flask import current_app


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in current_app.config["ALLOWED_EXTENSIONS"]


def store_upload(file_storage, folder: str) -> str:
    extension = file_storage.filename.rsplit(".", 1)[1].lower()
    target_dir = Path(current_app.config["UPLOAD_FOLDER"]) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    file_storage.save(target_dir / filename)
    return str(Path(folder) / filename)
