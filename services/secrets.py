"""Secret resolution helper.

Locally (and in any environment where the value is already present as an
environment variable, e.g. injected by Cloud Run's `--set-secrets` flag) we
just read `os.environ`. If the variable isn't set and a GCP project is
configured, we fall back to fetching the latest version from Secret Manager.
This lets the same code run unmodified on a laptop (with a `.env` file) and
on Cloud Run (with secrets mounted as env vars or fetched on demand).
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

_secret_manager_client = None


def _get_secret_manager_client():
    global _secret_manager_client
    if _secret_manager_client is None:
        from google.cloud import secretmanager

        _secret_manager_client = secretmanager.SecretManagerServiceClient()
    return _secret_manager_client


@lru_cache(maxsize=64)
def get_secret(name: str, *, required: bool = True, default: str | None = None) -> str | None:
    """Resolve a secret by logical name.

    Resolution order:
      1. Environment variable `name` (exact match).
      2. Secret Manager, using project id from `GOOGLE_CLOUD_PROJECT`, secret id
         `name`, version "latest".
    """

    value = os.environ.get(name)
    if value:
        return value

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        try:
            client = _get_secret_manager_client()
            secret_path = f"projects/{project_id}/secrets/{name}/versions/latest"
            response = client.access_secret_version(name=secret_path)
            return response.payload.data.decode("utf-8")
        except Exception:  # noqa: BLE001 - fall through to default/required handling
            pass

    if default is not None:
        return default
    if required:
        raise RuntimeError(
            f"Secret '{name}' is not set as an environment variable and could not be "
            "loaded from Secret Manager. Set it locally in your .env file or create "
            "the corresponding secret in Secret Manager."
        )
    return None


def add_secret_version(name: str, value: str) -> None:
    """Add a new version of a Secret Manager secret (used by the token-refresh
    job to rotate Instagram/LinkedIn access tokens without redeploying).

    No-ops with a log message if `GOOGLE_CLOUD_PROJECT` isn't set, since local
    dev typically manages tokens via `.env` by hand instead.
    """

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return

    client = _get_secret_manager_client()
    parent = f"projects/{project_id}/secrets/{name}"
    client.add_secret_version(parent=parent, payload={"data": value.encode("utf-8")})
    get_secret.cache_clear()

