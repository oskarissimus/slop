# slop config
# Define CONFIG as a dict matching AppConfig in `slop/config.py`
CONFIG = {
    "duration_seconds": 120,
    "fps": 24,
    "resolution_width": 1080,
    "resolution_height": 1920,
    "num_images": 12,
    "image_provider": "openai",  # uses Cursor env secret OPENAI_API_KEY
    "voice_id": "pNInz6obpgDQGcFmaJgB",
    "schedule": {
        "cron": "0 9 * * *"
    }
}