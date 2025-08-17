from __future__ import annotations

from typing import List
import json

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality


class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_script(topic: str, personality: Personality, target_duration_seconds: int) -> str:
    client = OpenAI()  # picks up OPENAI_API_KEY from env
    words_per_second = 2.5  # conservative speaking rate
    target_words = int(target_duration_seconds * words_per_second)
    prompt = (
        f"Napisz po polsku scenariusz lektorski do krótkiego, pionowego wideo w stylu Jana Chryzostoma Paska. "
        f"Persona narratora: {personality.name} ({personality.speaking_style}). {personality.description}. "
        f"Materiał źródłowy/temat: '{topic}'. "
        "Zachowaj gawędę sarmacką (pierwsza osoba, obrazowe anegdoty, umiarkowane archaizmy, klarowność). "
        "Uwzględnij, gdzie to zasadne: daty 1588 (Gravelines/Wielka Armada), 1603 (unia angielsko‑szkocka), 1632, 1648; "
        "postacie: Stefan Batory, Zygmunt III Waza, Władysław IV; instytucje: Rada Stanu, marszałek Rady, premier, naczelny wódz, "
        "ministrowie (stanu/dyplomacji, finansów, edukacji, skarbu), łącznicy z Sejmem; oraz wątek unii personalnej (polsko‑rosyjskiej vs polsko‑habsburskiej) "
        "i publicystyczny motyw „Bestii” (hipotezy oznaczaj: „wedle niektórych”). "
        f"Struktura skrótowa: hook, kontekst, 2–3 tezy, 1 dygresja sarmacka, echo współczesne po 2020 r., puenta. Długość około {target_words} słów. "
        "Nie dodawaj kierunków scenicznych ani znaczników czasu."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Piszesz zwięzłe, angażujące, około 2-minutowe skrypty lektorskie po polsku w stylistyce Jana Chryzostoma Paska."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=1200,
    )
    return response.choices[0].message.content.strip()


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_scenes(
    *,
    prompt_detail: str,
    personality: Personality,
    target_duration_seconds: int,
    num_scenes: int,
    model: str = "gpt-4o-mini",
) -> List[Scene]:
    """Generate a structured scenario as a list of scenes (script + image_description).

    The output is enforced as JSON using OpenAI's JSON mode. The style is Jan Chryzostom Pasek.
    """
    client = OpenAI()
    words_per_second = 2.5
    target_words = int(target_duration_seconds * words_per_second)

    system_msg = (
        "Jesteś pomocnikiem tworzącym scenariusze do krótkich pionowych wideo. "
        "Zawsze zwracasz poprawny JSON bez żadnego innego tekstu."
    )
    user_msg = (
        "Stwórz scenariusz w stylu Jana Chryzostoma Paska (barokowa sarmacka gawęda, pierwsza osoba, lekko archaiczny, "
        "ale zrozumiały dla współczesnych). Persona narratora: "
        f"{personality.name} ({personality.speaking_style}). {personality.description}. "
        f"Temat/uściślenie: {prompt_detail}. "
        "Uwzględnij, gdzie to zasadne, następujące elementy historyczne i instytucjonalne: "
        "1588 (Gravelines/Wielka Armada), 1603 (unia angielsko‑szkocka), 1632, 1648; "
        "Stefan Batory, Zygmunt III Waza, Władysław IV; Rada Stanu, marszałek Rady, premier, naczelny wódz, ministrowie (stanu/dyplomacji, finansów, edukacji, skarbu), "
        "łącznicy z Sejmem; unia personalna (polsko‑rosyjska vs polsko‑habsburska); publicystyczny motyw „Bestii” (hipotezy sygnalizuj: „wedle niektórych”). "
        f"Całkowita długość narracji około {target_words} słów. "
        f"Podziel treść dokładnie na {num_scenes} kolejnych scen. Każda scena MUSI mieć: "
        "- script: 1–3 zdania głośnego czytania (bez znaczników czasu). "
        "- image_description: 1–3 zdania opisu fotorealistycznego kadru bez jakiegokolwiek tekstu na obrazie. "
        "Zwróć wyłącznie JSON o schemacie: {\"scenes\":[{\"script\":str,\"image_description\":str}, ...]}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
        scenario = Scenario.model_validate(data)
        # Enforce exact number of scenes; truncate or pad with last
        scenes = list(scenario.scenes)
        if len(scenes) > num_scenes:
            scenes = scenes[:num_scenes]
        elif len(scenes) < num_scenes and scenes:
            while len(scenes) < num_scenes:
                scenes.append(scenes[-1])
        return scenes
    except (json.JSONDecodeError, ValidationError):
        # Fallback: produce a single-scene script, then replicate/pad
        fallback_script = generate_script(topic=prompt_detail, personality=personality, target_duration_seconds=target_duration_seconds)
        split = [s.strip() for s in fallback_script.split(".") if s.strip()]
        if not split:
            split = [fallback_script]
        # Group sentences into num_scenes buckets
        bucket_size = max(1, len(split) // max(1, num_scenes))
        buckets: List[str] = [" ".join(split[i:i+bucket_size]).strip() for i in range(0, len(split), bucket_size)]
        buckets = [b for b in buckets if b]
        while len(buckets) < num_scenes:
            buckets.append(buckets[-1])
        buckets = buckets[:num_scenes]
        return [Scene(script=b, image_description=b) for b in buckets]



