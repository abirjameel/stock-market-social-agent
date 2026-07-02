# Registering the Telegram webhook

After `deploy.sh` has deployed the service and you know its URL, point your
bot's webhook at it:

```bash
SERVICE_URL=$(gcloud run services describe market-social-agent \
  --region "$GOOGLE_CLOUD_LOCATION" --format='value(status.url)')

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${SERVICE_URL}/telegram/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"callback_query\"]"
```

`secret_token` must match the `TELEGRAM_WEBHOOK_SECRET` secret deployed to
Cloud Run - Telegram echoes it back on every webhook call as the
`X-Telegram-Bot-Api-Secret-Token` header, and `main.py` rejects any request
where it doesn't match.

## Sanity checks

```bash
# Confirm Telegram sees the webhook as registered:
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | jq

# Find your own numeric chat id (needed for TELEGRAM_CHAT_ID) by messaging
# the bot once, then:
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" | jq
```

## Removing the webhook (e.g. to debug locally with long-polling instead)

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```
