# Access & credentials setup checklist

Everything here is a prerequisite for the code to actually be able to post.
Several steps involve external review processes that run on the platform's
own timeline (days to weeks), not engineering time - start these as early as
possible, ideally in parallel with development. The code in this repo runs
against test/sandbox credentials until the production approvals land.

## 1. Google Cloud project

- [ ] Create or pick a GCP project; note its project id as `GOOGLE_CLOUD_PROJECT`.
- [ ] Enable billing (required for Cloud Run, Vertex AI).
- [ ] Enable APIs: `gcloud services enable run.googleapis.com cloudscheduler.googleapis.com firestore.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com`
- [ ] Create a Firestore database in **Native mode** (`gcloud firestore databases create --location=<region>`).
- [ ] Decide: use Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`, no API key needed, uses the Cloud Run service account) or the Gemini Developer API (`GEMINI_API_KEY` from https://aistudio.google.com/apikey). Vertex AI is recommended for production since there's no key to leak or rotate.

## 2. Telegram bot (fastest - do this first)

- [ ] Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, save the token as `TELEGRAM_BOT_TOKEN`.
- [ ] Message your new bot once (anything), then call `getUpdates` to find your numeric chat id -> `TELEGRAM_CHAT_ID` (see `deploy/telegram_webhook_setup.md`).
- [ ] Generate a random string for `TELEGRAM_WEBHOOK_SECRET` (e.g. `openssl rand -hex 24`).
- [ ] After first deploy, register the webhook per `deploy/telegram_webhook_setup.md`.

## 3. Dropbox

- [ ] Create an app at https://www.dropbox.com/developers/apps (choose "Scoped access", "App folder" or "Full Dropbox" access as you prefer).
- [ ] Under Permissions, enable `files.content.write`, `files.content.read`, `sharing.write`, `sharing.read`.
- [ ] Note the App key/secret -> `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET`.
- [ ] Generate a refresh token (one-time OAuth flow) so the app never needs manual token rotation:
  1. Visit `https://www.dropbox.com/oauth2/authorize?client_id=<APP_KEY>&token_access_type=offline&response_type=code`.
  2. Exchange the returned `code` for tokens:
     `curl https://api.dropboxapi.com/oauth2/token -d code=<CODE> -d grant_type=authorization_code -d client_id=<APP_KEY> -d client_secret=<APP_SECRET>`
  3. Save the `refresh_token` from the response as `DROPBOX_REFRESH_TOKEN`.
- [ ] (Fallback only) If you'd rather skip the refresh-token flow initially, generate a long-lived access token from the App Console and set `DROPBOX_ACCESS_TOKEN` directly - just know it will eventually need manual rotation.

## 4. Meta (Instagram Graph API) - budget 2-4 weeks for App Review

> Can't get Instagram credentials yet? Set `POST_TO_INSTAGRAM=false` in your
> env and skip this section entirely for now - `instagram_service.publish_post()`
> and the weekly token-refresh job both no-op cleanly without
> `INSTAGRAM_ACCESS_TOKEN`/`INSTAGRAM_BUSINESS_ACCOUNT_ID` configured, and
> LinkedIn publishing is unaffected. Flip it back to `true` once you have
> credentials.

- [ ] Create/use a Facebook Page for your brand.
- [ ] Convert your Instagram account to a **Business** or **Creator** account (Instagram app -> Settings -> Account type) and link it to the Facebook Page.
- [ ] Create a Meta app at https://developers.facebook.com/apps (type: Business).
- [ ] Add the **Instagram Graph API** product to the app.
- [ ] In Development mode, add yourself as a Test User/admin - you can already post as yourself for testing without waiting for review.
- [ ] Fetch your Instagram Business Account id (`INSTAGRAM_BUSINESS_ACCOUNT_ID`) via `GET /{fb-page-id}?fields=instagram_business_account&access_token=...`.
- [ ] Generate a User Access Token with `instagram_basic` + `instagram_content_publish`, then exchange it for a 60-day long-lived token -> `INSTAGRAM_ACCESS_TOKEN`.
- [ ] Submit for **App Review** for `instagram_basic` + `instagram_content_publish` once you're ready to post for real (screencast required showing the exact publish flow). This is the 2-4 week step - start it as soon as the integration works end-to-end against your own test account.

## 5. LinkedIn - budget 1-2+ weeks for organization posting; personal profile is faster

- [ ] Create an app at https://www.linkedin.com/developers/apps, linked to a Company Page you administer.
- [ ] Add the **Sign In with LinkedIn using OpenID Connect** product (self-serve) to authenticate and get `w_member_social` for **personal profile** posting.
- [ ] For **Company Page** posting, request the **Community Management API** (or Advertising API, depending on current LinkedIn product naming) product from the app's Products tab; this requires LinkedIn's approval of your use case (~1-2+ weeks, not guaranteed - have a fallback plan of personal-profile-only if this is denied).
- [ ] Run the OAuth 2.0 3-legged flow as an admin of the target Company Page, requesting scopes `w_member_social` (+ `w_organization_social` once approved), to get `LINKEDIN_ACCESS_TOKEN`.
- [ ] Get your person URN (`urn:li:person:{id}`) via `GET /v2/userinfo` (OpenID) and your organization URN (`urn:li:organization:{id}`) via `GET /rest/organizationAcls?q=roleAssignee`.
- [ ] Optional: ask LinkedIn for refresh-token rotation on your app so `services/token_refresh.py` can auto-refresh `LINKEDIN_ACCESS_TOKEN` (`LINKEDIN_REFRESH_TOKEN`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`); if not granted, plan to manually re-run the OAuth flow roughly every 60 days.

## 6. Market data / news (optional but recommended)

- [ ] `yfinance` needs no key.
- [ ] Sign up for a free Finnhub API key at https://finnhub.io/register -> `FINNHUB_API_KEY` (used for the news headlines that give the copy context; the pipeline still works without it, just with less color).

## 7. Load everything into Secret Manager

For each secret above:

```bash
printf '%s' "<value>" | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=- --project "$GOOGLE_CLOUD_PROJECT"
# ...repeat for TELEGRAM_WEBHOOK_SECRET, SCHEDULER_SECRET, DROPBOX_APP_KEY,
#    DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN, INSTAGRAM_ACCESS_TOKEN,
#    LINKEDIN_ACCESS_TOKEN, FINNHUB_API_KEY
```

Then grant the Cloud Run service account access:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"  # or a custom SA if you created one
for secret in TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET SCHEDULER_SECRET DROPBOX_APP_KEY DROPBOX_APP_SECRET DROPBOX_REFRESH_TOKEN INSTAGRAM_ACCESS_TOKEN LINKEDIN_ACCESS_TOKEN FINNHUB_API_KEY; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

`deploy/deploy.sh` also needs `token_refresh.py` to be able to *write* new
secret versions for `INSTAGRAM_ACCESS_TOKEN` (and `LINKEDIN_ACCESS_TOKEN` /
`LINKEDIN_REFRESH_TOKEN` if applicable) - grant `roles/secretmanager.secretVersionAdder`
on those specific secrets to the same service account as well.
