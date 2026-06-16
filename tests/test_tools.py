"""
tests/test_tools.py

One test per tool plus one per failure mode. The search tests are fully
offline. The LLM-backed tests (suggest_outfit, the create_fit_card happy path)
make real Groq calls, so they skip automatically if GROQ_API_KEY isn't set.
The empty-outfit guard test is offline — it never reaches the LLM.

Run from the repo root:  pytest tests/
To also see the printed output:  pytest -s tests/
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

needs_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping tests that call the LLM",
)


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    print(f"\n[returns_results] {len(results)} matches; top 3:")
    for item in results[:3]:
        print(f"   - {item['title']} (${item['price']})")
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    print(f"\n[empty_results] returned: {results}")
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    print(f"\n[price_filter] {len(results)} matches <= $10: "
          f"{[(i['title'], i['price']) for i in results]}")
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_loose():
    # "M" should still catch a listing labeled "S/M" or "M/L".
    results = search_listings("tee", size="M", max_price=None)
    print(f"\n[size_loose] sizes matched for 'M': "
          f"{sorted({i['size'] for i in results})}")
    assert all(
        "m" in {tok for tok in item["size"].lower().replace("/", " ").split()}
        for item in results
    )


# ── suggest_outfit ──────────────────────────────────────────────────────────

@needs_key
def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    print(f"\n[suggest_with_wardrobe] item={item['title']}\n{out}")
    assert isinstance(out, str)
    assert out.strip()


@needs_key
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe → still returns a useful, non-empty string.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    print(f"\n[suggest_empty_wardrobe] item={item['title']}\n{out}")
    assert isinstance(out, str)
    assert out.strip()


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: blank outfit → descriptive error string, no LLM call, no crash.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    print(f"\n[empty_outfit] returned: {result}")
    assert isinstance(result, str)
    assert result.strip()


def test_create_fit_card_whitespace_outfit():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("   ", item)
    print(f"\n[whitespace_outfit] returned: {result}")
    assert isinstance(result, str)
    assert result.strip()


@needs_key
def test_create_fit_card_varies():
    # Higher temperature should make repeated captions differ.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = "the tee with baggy jeans and chunky sneakers, denim jacket on top"
    caps = [create_fit_card(outfit, item) for _ in range(3)]
    print("\n[fit_card_varies] 3 captions:")
    for i, c in enumerate(caps, 1):
        print(f"   {i}. {c}")
    assert len(set(caps)) > 1
