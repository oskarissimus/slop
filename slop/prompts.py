"""
All prompts used in the slop video generation project.

This module centralizes all prompt templates and system messages used across the application.
"""

from __future__ import annotations


# ============================================================================
# TOPIC GENERATION PROMPTS
# ============================================================================

TOPIC_GENERATION_SYSTEM_MESSAGE = (
    "Tworzysz zwięzłe, angażujące polskie tytuły do krótkich pionowych wideo "
    "w stylistyce gawędy Jana Chryzostoma Paska (bez dosłownych cytatów)."
)

TOPIC_GENERATION_USER_PROMPT = (
    "Jesteś asystentem tworzącym tematy krótkich pionowych wideo. "
    "Zaproponuj jeden, chwytliwy i konkretny tytuł po polsku, odpowiedni dla ~2‑minutowego materiału. "
    "Styl: gawęda sarmacka Jana Chryzostoma Paska. "
    "Styl/nastrój tytułu: gawęda sarmacka Jana Chryzostoma Paska (pierwsza osoba, obrazowe anegdoty, "
    "lekko archaiczne słownictwo, ale zrozumiałe dla współczesnego odbiorcy). "
    "Nie odwołuj się do stałych list dat, postaci czy instytucji; trzymaj się bieżącego tematu i persony. "
    "Zwróć tylko tytuł, bez cudzysłowów."
)


## (Removed) Script generation prompts no longer used


# ============================================================================
# SCENE GENERATION PROMPTS
# ============================================================================

SCENE_GENERATION_SYSTEM_MESSAGE = (
    "Jesteś pomocnikiem tworzącym scenariusze do krótkich pionowych wideo. "
    "Zawsze zwracasz poprawny JSON bez żadnego innego tekstu."
)

def get_scene_generation_user_prompt(prompt_detail: str, target_words: int, num_scenes: int) -> str:
    """Generate user prompt for scene generation with structured JSON output."""
    return (
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


# ============================================================================
# IMAGE GENERATION PROMPTS
# ============================================================================

# Test prompts used for vertical image verification
VERTICAL_IMAGE_TEST_PROMPTS = [
    "Test vertical image, photorealistic portrait orientation, full-bleed, no borders",
    "Test vertical image 2, photorealistic portrait orientation, full-bleed, no borders",
]

