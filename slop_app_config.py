# slop config
# Define CONFIG as a dict matching AppConfig in `slop/config.py`
CONFIG = {
    "duration_seconds": 120,
    "fps": 24,
    "resolution_width": 1080,
    "resolution_height": 1920,
    "num_images": 12,
    "image_provider": "openai",
    "personality": {
        "name": "Curious Explorer",
        "description": "An upbeat, inquisitive narrator who explains concepts simply and vividly, with curiosity, positivity, and gentle humor.",
        "speaking_style": "warm, lively, friendly",
        "voice_id": "21m00Tcm4TlvDq8ikWAM"
    },
    "schedule": {
        "cron": "0 9 * * *"
    }
}