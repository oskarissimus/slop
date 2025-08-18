slop - AI video generator CLI

Setup
- Ensure Python 3.11+
- Copy `example.env` to `.env` and fill keys
- Install with uv: `uv sync`

CLI
- `slop run-once` generates a single 2-min video now
- Options: `--mode production|test` to switch cost/quality, `--prompt "opis tematu"` to pass manual topic

Environment
- `OPENAI_API_KEY` for LLM image prompts and scripts
- `ELEVENLABS_API_KEY` for TTS
- Optional overrides (production defaults preserved):
  - `SLOP_MODE` = `production` | `test` (in test we set `OPENAI_IMAGE_QUALITY=low` for `gpt-image-1` to reduce cost)
  - `OPENAI_CHAT_MODEL`, `OPENAI_SCENE_MODEL`
  - `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`
  - `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_TTS_FORMAT`
  - `SLOP_NUM_IMAGES`, `SLOP_FPS`, `SLOP_RESOLUTION_WIDTH`, `SLOP_RESOLUTION_HEIGHT`
  - `PROMPT` custom topic/description

Outputs
- Videos written under `outputs/` with timestamped filenames
