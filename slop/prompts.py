"""
All prompts used in the slop video generation project.

This module centralizes all prompt templates and system messages used across the application.
"""

from __future__ import annotations


## (Removed) Old topic-only generation prompts


# ============================================================================
# COMBINED TOPIC + SCENE GENERATION PROMPTS
# ============================================================================

COMBINED_GENERATION_SYSTEM_MESSAGE = (
	"Jesteś pomocnikiem tworzącym tematy i scenariusze do krótkich pionowych wideo. "
	"Zawsze zwracasz poprawny JSON bez żadnego innego tekstu."
)

def get_combined_generation_user_prompt(
	input_text: str,
	target_words: int,
	num_scenes: int,
) -> str:
	"""Generate user prompt for combined topic + scenes generation with structured JSON output."""
	base = (
		"Na podstawie poniższego opisu stwórz: \n"
		"1) zwięzły, chwytliwy polski tytuł (maks 120 znaków)\n"
		"2) scenariusz podzielony dokładnie na wskazaną liczbę scen.\n\n"
		f"Wejście użytkownika: {input_text or '(brak – zaproponuj własny ciekawy temat)'}\n\n"
		f"Całkowita długość narracji około {target_words} słów. "
		f"Podziel treść dokładnie na {num_scenes} kolejnych scen. Każda scena MUSI mieć: \n"
		"- script: 1–3 zdania głośnego czytania (bez znaczników czasu). \n"
		"- image_description: 1–3 zdania opisu fotorealistycznego kadru bez jakiegokolwiek tekstu na obrazie. Dodaj informację o kolorach, stylu, nastroju, a take szczegóły dotyczące postaci lub scenerii tak aby wszystkie obrazy tworzyły spójny obraz opowiadanej historii. \n"
		"Zwróć wyłącznie JSON o schemacie: {\"topic\": str, \"scenes\": [{\"script\": str, \"image_description\": str}, ...]}"
	)
	return base


# ============================================================================
# IMAGE GENERATION PROMPTS
# ============================================================================

# Test prompts used for vertical image verification
VERTICAL_IMAGE_TEST_PROMPTS = [
	"Test vertical image, photorealistic portrait orientation, full-bleed, no borders",
	"Test vertical image 2, photorealistic portrait orientation, full-bleed, no borders",
]

