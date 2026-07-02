#!/usr/bin/env bash
# Creates the two Cloud Scheduler jobs the pipeline needs:
#   1. daily-market-post   - triggers /generate once a day after US market close.
#   2. expire-stale-drafts - triggers /maintenance/expire-drafts hourly.
#
# Run after deploy.sh has deployed the service at least once.

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-market-social-agent}"
SCHEDULER_SECRET="${SCHEDULER_SECRET:?Set SCHEDULER_SECRET to the same value stored in Secret Manager}"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')

echo "Service URL: $SERVICE_URL"

# 21:30 UTC = 4:30pm ET, ~30 min after the US market close (4:00pm ET),
# leaving time for closing-price data to settle. Adjust the cron schedule /
# timezone to taste - e.g. run it in the morning instead if you'd rather
# recap "yesterday's close" before the next session opens.
gcloud scheduler jobs create http daily-market-post \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --schedule "30 21 * * 1-5" \
  --time-zone "UTC" \
  --uri "${SERVICE_URL}/generate" \
  --http-method POST \
  --headers "X-Scheduler-Secret=${SCHEDULER_SECRET}" \
  || echo "Job daily-market-post may already exist; run 'gcloud scheduler jobs update http ...' to change it."

gcloud scheduler jobs create http expire-stale-drafts \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --schedule "0 * * * *" \
  --time-zone "UTC" \
  --uri "${SERVICE_URL}/maintenance/expire-drafts" \
  --http-method POST \
  --headers "X-Scheduler-Secret=${SCHEDULER_SECRET}" \
  || echo "Job expire-stale-drafts may already exist; run 'gcloud scheduler jobs update http ...' to change it."

gcloud scheduler jobs create http refresh-social-tokens \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --schedule "0 6 * * 1" \
  --time-zone "UTC" \
  --uri "${SERVICE_URL}/maintenance/refresh-tokens" \
  --http-method POST \
  --headers "X-Scheduler-Secret=${SCHEDULER_SECRET}" \
  || echo "Job refresh-social-tokens may already exist; run 'gcloud scheduler jobs update http ...' to change it."

echo "Done."
