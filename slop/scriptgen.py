from __future__ import annotations

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_script(topic: str, personality: Personality, target_duration_seconds: int) -> str:
    client = OpenAI()  # picks up OPENAI_API_KEY from env
    words_per_second = 2.5  # conservative speaking rate
    target_words = int(target_duration_seconds * words_per_second)
    prompt = (
        f"Napisz po polsku scenariusz lektorski do krótkiego, pionowego wideo na temat: '{topic}'. "
        "Styl: Jan Chryzostom Pasek (barokowa sarmacka gawęda, narracja pierwszoosobowa, obrazowe anegdoty, "
        "lekko archaiczne słownictwo, ale zrozumiałe dla współczesnego odbiorcy). "
        f"Persona narratora: {personality.name} ({personality.speaking_style}). {personality.description}. "
        "Treść scenariusza ma fabularnie odtwarzać historię znaną z piosenki Franka Zappy 'Don't Eat the Yellow Snow' — "
        "nie cytuj ani nie tłumacz słów piosenki; opowiadaj własnymi słowami, zachowując kluczowe motywy: sen o byciu Eskimosem, trzaskający mróz, "
        "zorza polarna, matczyna przestroga, wskazówka by strzec się żółtego śniegu, humorystyczny ton. "
        f"Długość około {target_words} słów. Używaj żywych, konkretnych obrazów, naturalnego tempa; zakończ krótką klamrą. "
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



