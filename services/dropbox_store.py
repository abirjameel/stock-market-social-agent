"""Archives generated post images to Dropbox and produces a publicly
reachable direct-content URL (needed by the Instagram Graph API, which
requires a public `image_url` rather than accepting a raw upload).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import WriteMode
from dropbox.sharing import SharedLinkSettings

from services.config import config

_client: dropbox.Dropbox | None = None


@dataclass
class DropboxUploadResult:
    dropbox_path: str
    shared_link: str
    direct_link: str


def _get_client() -> dropbox.Dropbox:
    global _client
    if _client is not None:
        return _client

    refresh_token = config.dropbox_refresh_token()
    app_key = config.dropbox_app_key()
    app_secret = config.dropbox_app_secret()

    if refresh_token and app_key and app_secret:
        # Preferred: short-lived access token auto-refreshed via the SDK using
        # a long-lived refresh token, so we never need to babysit expiry.
        _client = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )
    else:
        # Fallback: static access token (simpler to set up, but expires and
        # must be regenerated manually in the Dropbox App Console).
        _client = dropbox.Dropbox(oauth2_access_token=config.dropbox_access_token())

    return _client


def _to_direct_link(shared_url: str) -> str:
    """Convert a Dropbox share URL (`?dl=0`) into a directly-fetchable image
    URL (`?raw=1`) that returns the raw file bytes without a Dropbox HTML
    preview page in between - required for the Instagram Graph API to be
    able to download the image."""

    if "?dl=0" in shared_url:
        return shared_url.replace("?dl=0", "?raw=1")
    if "?" in shared_url:
        return shared_url + "&raw=1"
    return shared_url + "?raw=1"


def upload_image(local_path: Path, remote_filename: str) -> DropboxUploadResult:
    dbx = _get_client()
    remote_path = f"{config.dropbox_folder.rstrip('/')}/{remote_filename}"

    with open(local_path, "rb") as f:
        dbx.files_upload(f.read(), remote_path, mode=WriteMode("overwrite"))

    try:
        link_metadata = dbx.sharing_create_shared_link_with_settings(
            remote_path, settings=SharedLinkSettings(requested_visibility=None)
        )
        shared_url = link_metadata.url
    except ApiError as exc:
        if exc.error.is_shared_link_already_exists():
            existing = dbx.sharing_list_shared_links(path=remote_path, direct_only=True)
            shared_url = existing.links[0].url
        else:
            raise

    return DropboxUploadResult(
        dropbox_path=remote_path,
        shared_link=shared_url,
        direct_link=_to_direct_link(shared_url),
    )


def download_image(dropbox_path: str) -> Path:
    """Download a previously archived image back to a local temp file.

    Needed at publish time because the Cloud Run instance that handles the
    Telegram approval webhook is very likely not the same instance (or even
    the same container) that originally rendered the image during
    `/generate`, so the original local temp file is long gone.
    """

    dbx = _get_client()
    _, response = dbx.files_download(dropbox_path)
    local_path = Path(tempfile.gettempdir()) / Path(dropbox_path).name
    local_path.write_bytes(response.content)
    return local_path
