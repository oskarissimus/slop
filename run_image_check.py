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
	# Provide explicit image prompts; automatic scene description is removed.
	image_prompts = [
		"Fotorealistyczna zimowa tundra o zmierzchu, śnieżna zamieć, husky w zaprzęgu, miękkie filmowe światło, pionowy kadr 9:16, brak tekstu.",
		"Wnętrze drewnianej chaty oświetlonej ogniem, stół z mapą i kompasem, detal dłoni przesuwającej figurę, głębia ostrości, brak tekstu.",
	]
	paths = generate_images(image_prompts=image_prompts, num_images=2, output_dir=out_dir)
	for p in paths:
		size = parse_png_size(Path(p))
		if size:
			w, h = size
			print(f"{p} -> {w}x{h} ({'vertical' if h > w else 'not vertical'})")
		else:
			print(f"{p} -> unknown size")


if __name__ == "__main__":
	main()