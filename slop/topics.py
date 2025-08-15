from __future__ import annotations

from typing import List

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality
from .utils import sanitize_title


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_topic(personality: Personality) -> str:
    client = OpenAI()
    prompt = (
        "Jesteś asystentem tworzącym tematy krótkich pionowych wideo. "
        "Zaproponuj jeden, chwytliwy i konkretny tytuł po polsku, odpowiedni dla ~2-minutowego materiału. "
        f"Persona: {personality.name}. Opis: {personality.description}. "
        "Motyw przewodni: śniłem, że jestem Eskimosem. "
        "Treść: ta sama oś fabularna co w piosence Franka Zappy 'Don't Eat the Yellow Snow' — nie cytuj tekstu piosenki, nawiązuj jedynie do zdarzeń. "
        "Styl/nastrój tytułu: gawęda sarmacka Jana Chryzostoma Paska (pierwsza osoba, obrazowe anegdoty, "
        "lekko archaiczne słownictwo, ale zrozumiałe dla współczesnego odbiorcy). "
        "Akcentuj: mroźną aurę, zorze polarne, przestrogę przed żółtym śniegiem, humor gawędziarski, element snu. "
        "Zwróć tylko tytuł, bez cudzysłowów."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tworzysz zwięzłe, angażujące polskie tytuły do krótkich wideo o motywie snu, że narrator jest Eskimosem, z fabułą inspirowaną piosenką Franka Zappy 'Don't Eat the Yellow Snow' (bez cytowania), stylizowane na gawędy Jana Chryzostoma Paska."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
        max_tokens=48,
    )
    raw = response.choices[0].message.content.strip()
    return sanitize_title(raw)



