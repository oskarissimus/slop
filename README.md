slop - AI video generator CLI

Setup
- Ensure Python 3.11+
- Copy `example.env` to `.env` and fill keys
- Install with uv: `uv sync`

CLI
- `slop init` creates a default config at `slop_app_config.py`
- `slop run-once` generates a single 2-min video now

Environment
- `OPENAI_API_KEY` for LLM image prompts and scripts
- `ELEVENLABS_API_KEY` for TTS

Outputs
- Videos written under `outputs/` with timestamped filenames
