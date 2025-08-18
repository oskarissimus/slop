import os
import json
import base64
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Import prompts from the slop module
sys.path.insert(0, str(Path(__file__).parent))
from slop.prompts import VERTICAL_IMAGE_TEST_PROMPTS


API_URL = "https://api.openai.com/v1/images/generations"
OUTPUT_DIR = Path("/workspace/outputs/verify_vertical")


def parse_png_size(data: bytes):
    sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(sig):
        return None
    # PNG: 8-byte signature, then 4-byte length, 4-byte type 'IHDR'
    # IHDR data: width (4), height (4)
    if len(data) < 24:
        return None
    # IHDR chunk starts at offset 8+8=16
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def parse_jpeg_size(data: bytes):
    # Minimal JPEG SOF0/SOF2 scan
    if not (len(data) > 2 and data[0] == 0xFF and data[1] == 0xD8):
        return None
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        # Skip padding FFs
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        # Standalone markers without length
        if marker in (0xD8, 0xD9):
            continue
        if i + 1 >= len(data):
            break
        seg_len = int.from_bytes(data[i:i+2], "big")
        if seg_len < 2:
            break
        if marker in (0xC0, 0xC2):  # SOF0, SOF2
            if i + 7 >= len(data):
                break
            # seg: [len(2)] [precision(1)] [height(2)] [width(2)] ...
            height = int.from_bytes(data[i+3:i+5], "big")
            width = int.from_bytes(data[i+5:i+7], "big")
            return width, height
        i += seg_len
    return None


def parse_image_size(data: bytes):
    parsers = (parse_png_size, parse_jpeg_size)
    for p in parsers:
        res = p(data)
        if res:
            return res
    return None


def generate_image(prompt: str, model: str, api_key: str) -> bytes:
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1792",
        "response_format": "b64_json",
    }
    req = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    b64 = data["data"][0]["b64_json"]
    return base64.b64decode(b64)


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY missing")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prompts = VERTICAL_IMAGE_TEST_PROMPTS

    results = []
    for idx, p in enumerate(prompts):
        try:
            # Try DALL·E 3 first, fallback to gpt-image-1
            try:
                img = generate_image(p, "dall-e-3", api_key)
            except HTTPError:
                img = generate_image(p, "gpt-image-1", api_key)
            out_path = OUTPUT_DIR / f"verify_{idx:02d}.png"
            with open(out_path, "wb") as f:
                f.write(img)
            size = parse_image_size(img)
            results.append((str(out_path), size))
        except (HTTPError, URLError) as e:
            print(f"HTTP error for image {idx}: {e}")
            sys.exit(2)

    for path, size in results:
        if size:
            w, h = size
            print(f"{path} -> {w}x{h} ({'vertical' if h > w else 'not vertical'})")
        else:
            print(f"{path} -> unknown size (could not parse)")


if __name__ == "__main__":
    main()