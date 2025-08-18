from __future__ import annotations

from typing import List
import json

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppConfig


class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_script(topic: str, target_duration_seconds: int) -> str:
    client = OpenAI()  # picks up OPENAI_API_KEY from env
    words_per_second = 2.5  # conservative speaking rate
    target_words = int(target_duration_seconds * words_per_second)
    prompt = (
        f"Napisz po polsku scenariusz lektorski do krótkiego, pionowego wideo w stylu Jana Chryzostoma Paska. "
        f"Materiał źródłowy/temat: '{topic}'. "
        f" Długość około {target_words} słów. "
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
        "Stwórz scenariusz w stylu Jana Chryzostoma Paska "
        f"Temat/uściślenie: {prompt_detail}. "
        "opowiedz w stylu Jana Chryzostoma paska historie z piosenki nanook rubs it franka zappy. Well, right about that time, people\n"
        "A fur trapper who was strictly from commercial\n"
        "(Strictly commercial)\n"
        "Had the unmitigated audacity to jump up from behind my igloo\n"
        "(Peek-a-boo, whoo-ooh-ooh)\n"
        "And he started in to whippin' on my favorite baby seal\n"
        "With a lead-filled snow shoe\n"
        "I said with a lead (lead)\n"
        "Filled (lead-filled)\n"
        "A lead-filled snow shoe (snow shoe)\n"
        "He said \"Peek-a-boo\" (peek-a-boo)\n"
        "With a lead (lead)\n"
        "Filled (lead-filled)\n"
        "With a lead-filled snow shoe (snow shoe)\n"
        "He said \"Peek-a-boo\" (peek-a-boo)\n"
        "He went right up side the head of my favourite baby seal\n"
        "He went whap with a lead-filled snow shoe\n"
        "And he hit him on the nose and he hit him on fin and he -\n"
        "That got me just about as evil as an Eskimo boy can be\n"
        "So I bent down and I reached down and I scooped down\n"
        "And I gathered up a generous mitten full of the deadly (yellow snow)\n"
        "The deadly yellow snow from right there where the huskies go\n"
        "Whereupon I proceeded to take that mittenful of the deadly yellow snow crystals\n"
        "And rub it all into his beady little eyes with a vigorous circular motion\n"
        "Hitherto unknown to the people in this area\n"
        "But destined to take the place of the mud shark in your mythology\n"
        "Here it goes now, the circular motion, rub it\n"
        "(Here Fido, here Fido)\n"
        "And then, in a fit of anger, I, I pounced\n"
        "And I pounced again\n"
        "Great googly-moogly\n"
        "I jumped up and down the chest of the\n"
        "I injured the fur trapper\n"
        "Well, he was very upset, as you can understand\n"
        "And rightly so, because the deadly yellow snow crystals\n"
        "Had deprived him of his sight\n"
        "And he stood up and he looked around\n"
        "And he said, \"I can't see\" (do, do do-do do do-do, yeah)\n"
        "\"I can't see\" (do, do do-do do do-do, yeah)\n"
        "\"Oh, woe is me\" (do, do do-do do do-do, yeah)\n"
        "\"I can't see\" (do, do do-do do do-do, well)\n"
        "No, no\n"
        "I can't see\n"
        "No, I\n"
        "He took a dog-doo sno-cone and stuffed it in my right eye\n"
        "He took a dog-doo sno-cone and stuffed it in my other eye\n"
        "And the huskie wee-wee, I mean the doggie wee-wee, has blinded me\n"
        "And I can't see\n"
        "Temporarily\n"
        "Well, the fur trapper stood there\n"
        "With his arms outstretched\n"
        "Across the frozen white wasteland\n"
        "Trying to figure out what he's gonna do about his deflicted eyes\n"
        "And it was at that precise moment that he remembered an ancient Eskimo legend\n"
        "Wherein it is written and whatever it is that they write it on up there\n"
        "That if anything bad ever happens to your eyes\n"
        "As a result of some sort of conflict with anyone named Nanook\n"
        "The only way you can get it fixed up\n"
        "Is to go trudgin' across the tundra, mile after mile\n"
        "Trudgin' across the tundra\n"
        "Right down to the parish of Saint Alfonzo\n"
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
        fallback_script = generate_script(topic=prompt_detail, target_duration_seconds=target_duration_seconds)
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



