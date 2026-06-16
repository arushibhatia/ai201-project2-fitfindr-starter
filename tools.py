"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

# Small set of filler words we don't want to score on — they'd match almost
# everything and add noise. "size" is here because the parsed description
# occasionally carries it over.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "or", "of", "in", "to",
    "my", "i", "im", "looking", "want", "size", "some", "any",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _listing_text_tokens(item: dict) -> list[str]:
    """Flatten a listing's text fields into one list of word tokens."""
    parts = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("category", ""),
        item.get("brand") or "",
        " ".join(item.get("style_tags", [])),
        " ".join(item.get("colors", [])),
    ]
    return _tokenize(" ".join(parts))


def _format_item(item: dict) -> str:
    """One-line summary of a listing for use inside an LLM prompt."""
    colors = ", ".join(item.get("colors", []))
    tags = ", ".join(item.get("style_tags", []))
    return (
        f"{item.get('title', 'Unknown item')} "
        f"(category: {item.get('category', 'n/a')}; "
        f"colors: {colors or 'n/a'}; "
        f"style: {tags or 'n/a'})"
    )


def _format_wardrobe_item(w: dict) -> str:
    """One-line summary of a wardrobe item for use inside an LLM prompt."""
    colors = ", ".join(w.get("colors", []))
    note = w.get("notes")
    summary = f"{w.get('name', 'item')} ({w.get('category', 'n/a')}, {colors or 'n/a'})"
    return f"{summary} — {note}" if note else summary


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Keywords we'll score listings against (filler words removed).
    keywords = [t for t in _tokenize(description or "") if t not in _STOPWORDS]

    # Loose, case-insensitive size tokens, e.g. "M" -> {"m"}, "S/M" -> {"s", "m"}.
    wanted_size = set(_tokenize(size)) if size else set()

    scored = []
    for item in listings:
        # Price filter (inclusive). Skip listings over the ceiling.
        if max_price is not None and item.get("price", 0) > max_price:
            continue

        # Size filter: keep the listing if any of its size tokens match.
        if wanted_size:
            item_size = set(_tokenize(item.get("size", "")))
            if not (wanted_size & item_size):
                continue

        # Relevance: rank by how many distinct keywords appear, then by how
        # many times they appear in total. Whole-word, case-insensitive.
        item_tokens = _listing_text_tokens(item)
        distinct = sum(1 for k in set(keywords) if k in item_tokens)
        if distinct == 0:
            continue
        mentions = sum(item_tokens.count(k) for k in keywords)
        scored.append(((distinct, mentions), item))

    # Highest score first; stable sort keeps dataset order for ties.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = _format_item(new_item)
    items = (wardrobe or {}).get("items", [])

    if not items:
        # Empty wardrobe: no pieces to name, so give general styling advice.
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They haven't told us anything about their existing wardrobe yet. "
            "In 2-3 sentences, suggest how to style this piece in general — what "
            "kinds of pieces pair well with it and what vibe it suits. Casual and "
            "friendly, like a stylist giving quick advice. Keep it short. "
            "Do not invent specific items they own."
        )
    else:
        # Wardrobe present: name real pieces from it in the suggestions.
        wardrobe_desc = "\n".join(f"- {_format_wardrobe_item(w)}" for w in items)
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Here is what's already in their wardrobe:\n{wardrobe_desc}\n\n"
            "Suggest one complete outfit (you may add a quick alternative) that "
            "pairs the new item with specific pieces from their wardrobe. Name the "
            "wardrobe pieces you use. Keep it to 2-3 short sentences, casual and "
            "friendly, like a stylist talking them through it."
        )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=180,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: no outfit to caption — return a clear message, don't call the LLM.
    if not outfit or not outfit.strip():
        return (
            "Can't make a fit card yet — there's no outfit to caption. "
            "Find an item and get a styling suggestion first."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "")
    price_str = f"${price:g}" if price is not None else "a steal"

    prompt = (
        "Write a short, shareable caption for a thrifted outfit, the kind "
        "someone would post with an OOTD photo.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- 1 to 2 short sentences, like a real caption — NOT a product description.\n"
        f"- Mention the item name, the price ({price_str}), and the platform "
        f"({platform}) naturally, once each.\n"
        "- Capture the vibe of the outfit in specific terms.\n"
        "- Sound like a real person, lowercase and a little playful is fine.\n"
        "Return only the caption text."
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
        max_tokens=90,
    )
    return response.choices[0].message.content.strip()
