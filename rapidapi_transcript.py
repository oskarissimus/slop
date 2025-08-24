import os
import sys
import json
import requests

# Accept RAPIDAPI_KEY or X_RAPIDAPI_KEY from environment
RAPID_KEY = os.getenv("RAPIDAPI_KEY") or os.getenv("X_RAPIDAPI_KEY")
if not RAPID_KEY:
	print("Missing RAPIDAPI_KEY or X_RAPIDAPI_KEY in environment", file=sys.stderr)
	sys.exit(2)

VIDEO_URL = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/OVosXx5lXmw"
API_URL = "https://youtube-transcription-api-and-youtube-translation-api.p.rapidapi.com/transcribe"

headers = {
	"content-type": "application/json",
	"X-RapidAPI-Key": RAPID_KEY,
}

payload = {"url": VIDEO_URL}

try:
	resp = requests.post(API_URL, headers=headers, json=payload, timeout=90)
	if resp.status_code != 200:
		print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
		sys.exit(1)
	data = resp.json()
	# Try common fields
	transcript = data.get("transcription") or data.get("transcript") or data.get("data") or data
	if isinstance(transcript, (list, dict)):
		print(json.dumps(transcript, ensure_ascii=False, indent=2))
	else:
		print(transcript)
except Exception as e:
	print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
	sys.exit(3)
