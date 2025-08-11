## AI Video Generator (GCF)

Generates a ~2-minute AI slideshow video on a schedule:
- Topic + script via OpenAI
- Voiceover via ElevenLabs
- Images via OpenAI Images
- Stitch with ffmpeg
- Upload to YouTube
- Runs as Google Cloud Function (Gen 2), triggered by Cloud Scheduler

### Services and APIs needed
- Google Cloud:
  - Cloud Functions (Gen 2)
  - Cloud Run (managed by CF)
  - Cloud Build
  - Eventarc
  - Cloud Scheduler
  - IAM
- YouTube Data API v3 (in Google Cloud Console for the OAuth client)
- OpenAI API (key)
- ElevenLabs API (key)

### What you provide (secrets/vars)
- OpenAI: `OPENAI_API_KEY`
- ElevenLabs: `ELEVENLABS_API_KEY`
- YouTube OAuth:
  - `YOUTUBE_CLIENT_ID`
  - `YOUTUBE_CLIENT_SECRET`
  - `YOUTUBE_REFRESH_TOKEN`
  - `YOUTUBE_REDIRECT_URI` (same one used to issue the refresh token)
- GCP deployment:
  - `GCP_PROJECT_ID` (secret)
  - `GCP_REGION` (secret, e.g. `us-central1`)
  - `GCP_SA_KEY` (secret: JSON of a deployer service account with roles: Cloud Functions Admin, Cloud Run Admin, Service Account User, Cloud Scheduler Admin)
- Scheduler security (optional but recommended):
  - `CRON_SECRET` (secret, any strong string). Scheduler sends it as `x-cron-secret` header.
- Optional org settings (GitHub Actions Variables):
  - `VIDEO_CRON_SCHEDULE` (e.g., `0 14 * * *`)
  - `VOICE_ID` (ElevenLabs voice ID)
  - `PERSONALITY_PROMPT`
  - `IMAGE_MODEL` (`gpt-image-1`)
  - `VIDEO_PRIVACY_STATUS` (`public` | `unlisted` | `private`)
  - `TOPIC_TAGS` (comma-separated)
  - `NUM_IMAGES` (default 8)
  - `TARGET_SECONDS` (default 120)
  - `SCHEDULER_SA_EMAIL` (optional: Service account for Cloud Scheduler OIDC)

Create `.env` for local dev or set env vars directly. Example in `config/config.example.json`.

### One-time setup
1. In GCP, enable APIs:
   - Cloud Functions, Cloud Run, Cloud Build, Eventarc, Cloud Scheduler
2. Create a service account for GitHub Actions. Grant roles:
   - Cloud Functions Admin, Cloud Run Admin, Service Account User, Cloud Scheduler Admin
   - Optionally: Viewer for discovery
   - Create key and store JSON in GitHub secret `GCP_SA_KEY`
3. Create OAuth credentials for YouTube (type: Desktop or Web). Enable YouTube Data API v3 on your project.
   - Generate a refresh token for the channel to upload to
   - Store `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_REDIRECT_URI` in GitHub secrets
4. Get your ElevenLabs `VOICE_ID` and API key.
5. Get your OpenAI API key.

### Deploy
Push to `master`/`main` or merge a PR. The GitHub Action will:
- Deploy the Cloud Function (Gen 2)
- Retrieve the function URL
- Create/Update a Cloud Scheduler job with your cron and OIDC auth, attaching `x-cron-secret`
- Grant Cloud Run invoker to the Scheduler service account

### Local test
```bash
npm install
export $(cat config/config.example.json | jq -r 'to_entries|map("\(.key)=\(.value)")|.[]')
npm run start
# Then curl locally:
curl -H "x-cron-secret: $CRON_SECRET" http://localhost:8080/
```

### Notes
- Duration targeting: The script targets ~2 minutes. The slideshow image durations are evenly distributed to match the generated audio length. Final video is cut to audio length.
- Temporary files are written to `/tmp` as required by Cloud Functions.
- If you prefer Stability AI or other image providers, replace `generateImages` accordingly.
- The function requires outbound internet to call APIs.