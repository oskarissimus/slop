import os
from pathlib import Path
from slop.images import generate_images

# Minimal PNG size parser

def parse_png_size(path: Path):
	data = path.read_bytes()
	sig = b"\x89PNG\r\n\x1a\n"
	if not data.startswith(sig) or len(data) < 24:
		return None
	w = int.from_bytes(data[16:20], "big")
	h = int.from_bytes(data[20:24], "big")
	return w, h


def main():
	os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
	out_dir = Path("/workspace/outputs/app_check")
	out_dir.mkdir(parents=True, exist_ok=True)
	script = "Krótki test generacji obrazów do wideo pionowego."
	paths = generate_images(script_text=script, num_images=2, output_dir=out_dir, provider="openai")
	for p in paths:
		size = parse_png_size(Path(p))
		if size:
			w, h = size
			print(f"{p} -> {w}x{h} ({'vertical' if h > w else 'not vertical'})")
		else:
			print(f"{p} -> unknown size")


if __name__ == "__main__":
	main()