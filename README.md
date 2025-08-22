slop - AI video generator CLI

Setup
- Ensure Python 3.11+
- Copy `example.env` to `.env` and fill keys
- Install with uv: `uv sync`

CLI
- `slop run-once` generates a single 2-min video now
- Options: `--prompt "opis tematu"` to pass manual topic
- If neither `--prompt` nor `--prompt-file` is provided, `./prompt.txt` is auto-read (if present)
- Special mode: include the phrase "business as usual" in the prompt (or in `prompt.txt`) to fetch recent YouTube uploads with views, likes, and comments and feed a summary to the LLM to propose a new topic aimed at maximizing engagement

Environment
- `OPENAI_API_KEY` for LLM image prompts and scripts
- `ELEVENLABS_API_KEY` for TTS
- Optional overrides:
  - `OPENAI_CHAT_MODEL`, `OPENAI_SCENE_MODEL`
  - `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`
  - `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_TTS_FORMAT`
  - `SLOP_NUM_IMAGES`, `SLOP_FPS`, `SLOP_RESOLUTION_WIDTH`, `SLOP_RESOLUTION_HEIGHT`
  - `PROMPT` custom topic/description

Outputs
- Videos written under `outputs/` with timestamped filenames
