## Privacy Policy

Effective date: 2025-08-28

Thank you for using Slop (the “App”). This Privacy Policy explains what information the App accesses, how it is used, and your choices. By using the App, you agree to this Policy.

If you are publishing this App via Google OAuth for YouTube access, this Policy is intended to satisfy the Google API Services User Data Policy, including the YouTube API Services Terms of Service and the Limited Use requirements.

### Overview
- **App purpose**: Generate media and optionally upload videos to your YouTube channel, and/or read analytics to help you evaluate content performance.
- **Where it runs**: The App is typically run locally by you. Unless you deploy it to your own server, data and credentials are stored on your own machine.

### Information We Access
Depending on which features you use, the App may access:
- **Google/YouTube account information via OAuth**: limited to the scopes you grant during the Google consent flow.
- **YouTube channel and video metadata**: channel ID, video IDs, titles, descriptions, thumbnails, tags.
- **YouTube analytics metrics (if enabled)**: views, impressions, likes, comments counts, watch time, audience and traffic metrics provided by the YouTube Analytics API.
- **Content you provide**: prompts, scripts, images, audio, and generated media files stored under the project’s `outputs/` directory.
- **Authentication tokens**: OAuth tokens needed to access Google/YouTube on your behalf.

The App does not intentionally collect sensitive personal data such as government IDs, financial information, or precise geolocation.

### How We Use Information
- **Provide core functionality**: authenticate with Google/YouTube, upload videos, manage metadata, and (optionally) read analytics.
- **Content generation**: use your prompts and inputs to generate media assets that you explicitly create.
- **Local operation**: store your OAuth tokens locally to enable your chosen features.

We do not sell your data.

### Google User Data and YouTube Data API
When you connect a Google account, the App uses OAuth 2.0 and requests only the minimum scopes necessary for the features you choose. Typical scopes may include:

- `https://www.googleapis.com/auth/youtube.upload` (upload videos)
- `https://www.googleapis.com/auth/youtube.readonly` (read channel/video metadata)
- `https://www.googleapis.com/auth/yt-analytics.readonly` (read analytics)

The exact scopes requested are shown on the Google consent screen. You can refuse any non-essential scopes.

We comply with the Google API Services User Data Policy, including the Limited Use requirements:
- Google user data is used solely to provide or improve features within the App (e.g., upload videos, read analytics) and not for serving ads.
- We do not transfer Google user data to third parties except as necessary to provide the App’s functionality, comply with the law, or with your explicit direction.
- We do not sell Google user data.

### Data Storage and Retention
- **Local storage**: By default, OAuth credentials are stored locally on your machine in `token.json` within the project directory. Generated media and intermediate files are stored under `outputs/`.
- **Server deployments**: If you deploy the App to your own server, you are responsible for securing storage (e.g., encrypting tokens and restricting access).
- **Retention**: Data is retained only as long as needed for the features you use. You may delete local files at any time.

### Sharing of Information
We do not share or sell your personal information. The App may use third-party service providers to process media (for example, text-to-speech or image generation services) if you enable or configure them. In those cases, only the minimum data required for the requested operation is sent to the respective provider, under their terms. Replace or remove any providers you do not wish to use in your own deployment.

### Your Choices and Controls
- **Revoke Google access**: You can revoke the App’s access at any time via your Google Account settings: [Google Account — Third-party access](https://myaccount.google.com/permissions).
- **Delete local data**: Remove `token.json`, any cached credentials, and files in `outputs/` to delete locally stored data.
- **Scopes**: Decline non-essential OAuth scopes during the consent flow.

### Data Security
We take reasonable measures to protect information processed by the App. Because you typically run the App locally, you are responsible for securing your device, project directory, and any deployments you host. No method of transmission or storage is 100% secure.

### Children’s Privacy
The App is not directed to children under 13, and we do not knowingly collect personal information from children.

### International Users
If you deploy or use the App outside your country, you are responsible for ensuring compliance with local laws. Data may be processed in the country where you run or host the App and where any third-party providers you enable operate.

### Changes to This Policy
We may update this Privacy Policy to reflect changes in the App or applicable laws. Material changes will be noted by updating the “Effective date” above. Your continued use of the App after changes means you accept the updated Policy.

### Contact
If you have questions or requests (including access, correction, or deletion requests), contact:

Email: privacy@example.com

If you are using the App solely on your own machine and not providing it as a service to others, you may replace the contact with your own details or remove it.

### Additional Notes for Review (Google/YouTube)
- This App uses OAuth 2.0 for user authentication.
- It requests only the scopes necessary for video upload and/or analytics, as shown on the consent screen.
- User tokens and data are stored locally in the project directory by default and are not transmitted to a centralized server unless the user deploys their own instance and configures it to do so.

