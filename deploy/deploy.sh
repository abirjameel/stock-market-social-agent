#!/usr/bin/env bash
# Builds and deploys the service to Cloud Run, wiring up secrets from Secret
# Manager, provisioning the Cloud Storage bucket used to archive post images,
# and granting the runtime service account the IAM roles it needs. Run from
# the repo root: `bash deploy/deploy.sh`.
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
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:?Set GCS_BUCKET_NAME (must be globally unique)}"
# Only needed if you named your Firestore database something other than the
# implicit "(default)" when you created it in the Cloud Console.
FIRESTORE_DATABASE_ID="${FIRESTORE_DATABASE_ID:-(default)}"

echo "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT_ID"

echo "Ensuring Cloud Storage bucket gs://$GCS_BUCKET_NAME exists with public read access..."
gcloud storage buckets describe "gs://$GCS_BUCKET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$GCS_BUCKET_NAME" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --uniform-bucket-level-access

# Public read on every object in the bucket - required so Instagram's Graph
# API can fetch `image_url` without any auth. Safe to re-run (idempotent).
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET_NAME" \
  --member="allUsers" \
  --role="roles/storage.objectViewer"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Granting the runtime service account ($RUNTIME_SA) the roles it needs..."
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET_NAME" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/datastore.user" \
  --condition=None
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/aiplatform.user" \
  --condition=None

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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID" \
  --set-secrets "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,\
SCHEDULER_SECRET=SCHEDULER_SECRET:latest,\
INSTAGRAM_ACCESS_TOKEN=INSTAGRAM_ACCESS_TOKEN:latest,\
LINKEDIN_ACCESS_TOKEN=LINKEDIN_ACCESS_TOKEN:latest,\
FINNHUB_API_KEY=FINNHUB_API_KEY:latest"

echo "Done. Fetch the service URL with:"
echo "  gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
