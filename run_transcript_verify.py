from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

from slop.youtube_monitor import YouTubePublicMonitor, fetch_transcript_text


def main() -> None:
	load_dotenv()
	creds_dir = Path(os.getenv("YOUTUBE_CREDENTIALS_DIR") or Path.cwd())
	handle = os.getenv("VERIFY_CHANNEL_HANDLE", "@swaruuofficial")
	freshness_hours = int(os.getenv("VERIFY_FRESHNESS_HOURS", "2400"))

	monitor = YouTubePublicMonitor(credentials_dir=creds_dir)
	channel_id = monitor.resolve_channel_id(handle)
	if not channel_id:
		print("channel_id: <none>")
		raise SystemExit(2)

	videos = monitor.fetch_recent_videos(channel_id, max_results=5)
	now = datetime.now(timezone.utc)

	print(f"channel_id: {channel_id}")
	for v in videos:
		pub_dt = datetime.fromisoformat(v.published_at.replace("Z", "+00:00")) if v.published_at else None
		is_fresh = bool(pub_dt) and ((now - pub_dt) <= timedelta(hours=freshness_hours))
		print(f"candidate: {v.video_id} | {v.title} | {v.published_at} | fresh={is_fresh}")

	# Try in order and stop at the first with a transcript
	for v in videos:
		tx = fetch_transcript_text(v.video_id, preferred_languages=None, use_generated_fallback=True)
		if tx:
			print("selected_video_id:", v.video_id)
			print("transcript_chars:", len(tx))
			print("transcript_preview:", tx[:300].replace("\n", " "))
			return

	# Fallback to single latest if none returned above
	latest = monitor.fetch_latest_video(channel_id)
	if latest:
		tx = fetch_transcript_text(latest.video_id, preferred_languages=None, use_generated_fallback=True)
		if tx:
			print("selected_video_id:", latest.video_id)
			print("transcript_chars:", len(tx))
			print("transcript_preview:", tx[:300].replace("\n", " "))
			return

	print("No transcript found for recent uploads.")
	raise SystemExit(1)


if __name__ == "__main__":
	main()