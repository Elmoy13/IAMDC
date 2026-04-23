"""Mood Kit system — visual personality presets for slide decks.

Each mood kit provides layout functions keyed by slide type that produce
visually distinct elements matching a brand personality archetype.
"""
from app.services.mood_kits.bold import BOLD_LAYOUTS
from app.services.mood_kits.editorial import EDITORIAL_LAYOUTS
from app.services.mood_kits.playful import PLAYFUL_LAYOUTS
from app.services.mood_kits.minimal import MINIMAL_LAYOUTS

MOOD_REGISTRY: dict[str, dict] = {
    "BOLD": BOLD_LAYOUTS,
    "EDITORIAL": EDITORIAL_LAYOUTS,
    "PLAYFUL": PLAYFUL_LAYOUTS,
    "MINIMAL": MINIMAL_LAYOUTS,
}

__all__ = ["MOOD_REGISTRY"]
