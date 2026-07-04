"""Archives generated post images to a Google Cloud Storage bucket and
produces a publicly reachable URL (needed by the Instagram Graph API, which
requires a public `image_url` rather than accepting a raw upload).

Uses the same Application Default Credentials as `services.firestore_store`
(the Cloud Run service's runtime service account in production, or a local
service-account key / `gcloud auth application-default login` for local
dev) - no separate OAuth flow, no access tokens to refresh or expire.

The target bucket must be created ahead of time with public read access on
its objects (see docs/ACCESS_SETUP_CHECKLIST.md) - this module does not
attempt to create the bucket or change its IAM policy.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from google.cloud import storage

from services.config import config

_client: storage.Client | None = None


@dataclass
class GCSUploadResult:
    blob_path: str
    public_url: str


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client(project=config.gcp_project or None)
    return _client


def _bucket() -> storage.Bucket:
    return _get_client().bucket(config.gcs_bucket_name)


def upload_image(local_path: Path, remote_filename: str) -> GCSUploadResult:
    blob_path = f"{config.gcs_folder.strip('/')}/{remote_filename}"
    blob = _bucket().blob(blob_path)
    blob.upload_from_filename(str(local_path), content_type="image/jpeg")

    public_url = f"https://storage.googleapis.com/{config.gcs_bucket_name}/{blob_path}"
    return GCSUploadResult(blob_path=blob_path, public_url=public_url)


def download_image(blob_path: str) -> Path:
    """Download a previously archived image back to a local temp file.

    Needed at publish time because the Cloud Run instance that handles the
    Telegram approval webhook is very likely not the same instance (or even
    the same container) that originally rendered the image during
    `/generate`, so the original local temp file is long gone.
    """

    blob = _bucket().blob(blob_path)
    local_path = Path(tempfile.gettempdir()) / Path(blob_path).name
    blob.download_to_filename(str(local_path))
    return local_path
