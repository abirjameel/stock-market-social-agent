#!/usr/bin/env bash
# Builds and deploys the service to Cloud Run, wiring up secrets from Secret
# Manager. Run from the repo root: `bash deploy/deploy.sh`.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project "$GOOGLE_CLOUD_PROJECT"
#   Secret Manager secrets already created (see below) and the Cloud Run
#   service account granted `roles/secretmanager.secretAccessor` on each.

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-market-social-agent}"

echo "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  --project "$PROJECT_ID"

echo "Deploying $SERVICE_NAME to Cloud Run in $REGION..."
# NOTE: --allow-unauthenticated is required because Telegram's webhook must
# be able to reach this service over plain HTTPS with no GCP credentials.
# /generate and /maintenance/expire-drafts are instead protected by the
# app-level X-Scheduler-Secret header (see main.py + scheduler_setup.sh), and
# /telegram/webhook is protected by Telegram's own X-Telegram-Bot-Api-Secret-Token
# header. Do not skip setting SCHEDULER_SECRET and TELEGRAM_WEBHOOK_SECRET.
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 300 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true" \
  --set-secrets "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,\
SCHEDULER_SECRET=SCHEDULER_SECRET:latest,\
DROPBOX_APP_KEY=DROPBOX_APP_KEY:latest,\
DROPBOX_APP_SECRET=DROPBOX_APP_SECRET:latest,\
DROPBOX_REFRESH_TOKEN=DROPBOX_REFRESH_TOKEN:latest,\
INSTAGRAM_ACCESS_TOKEN=INSTAGRAM_ACCESS_TOKEN:latest,\
LINKEDIN_ACCESS_TOKEN=LINKEDIN_ACCESS_TOKEN:latest,\
FINNHUB_API_KEY=FINNHUB_API_KEY:latest"

echo "Done. Fetch the service URL with:"
echo "  gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
