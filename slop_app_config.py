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
        "name": "Sarmacki Gawędziarz",
        "description": "Ciepły, niski, męski głos starego szlachcica-gawędziarza; barwne anegdoty, serdeczny ton, dystyngowana swada, lekka ironia.",
        "speaking_style": "ciepły, niski, spokojny, gawędziarski, ojcowski",
        "voice_id": "pNInz6obpgDQGcFmaJgB"
    },
    "schedule": {
        "cron": "0 9 * * *"
    }
}