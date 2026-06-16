"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    _get_groq_client,
)


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Ask the LLM to pull search parameters out of a natural-language request.

    Returns a dict with:
        description (str)        — item keywords, "" if nothing to search for
        size (str or None)       — size token, or None if not mentioned
        max_price (float or None)— price ceiling, or None if not mentioned
    """
    prompt = (
        "Extract search parameters from this thrifting request. "
        "Respond with a JSON object with exactly these keys:\n"
        '- "description": a short string of item keywords (e.g. '
        '"vintage graphic tee"). Empty string if there is nothing to search for.\n'
        '- "size": the size as a string (e.g. "M", "8"), or null if not mentioned.\n'
        '- "max_price": the max price as a number, or null if not mentioned.\n\n'
        f"Request: {query}"
    )
    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)

    description = (data.get("description") or "").strip()

    size = data.get("size")
    if isinstance(size, str):
        size = size.strip() or None

    max_price = data.get("max_price")
    if isinstance(max_price, str):
        try:
            max_price = float(max_price)
        except ValueError:
            max_price = None

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── step logging ──────────────────────────────────────────────────────────────

def _make_logger(verbose: bool, step: bool):
    """
    Build a (log, pause) pair for narrating a run.

    log(msg)   prints msg only when verbose is on.
    pause(msg) waits for Enter before the next step when step is on, so a
               presenter can talk over each step during a live demo.
    """
    def log(msg: str = "") -> None:
        if verbose:
            print(msg)

    def pause(label: str) -> None:
        if step:
            input(f"   ⏎ press Enter to {label} ")

    return log, pause


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict, verbose: bool = False,
              step: bool = False) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py
        verbose:  When True, print what the agent does at each step (useful
                  for the demo). Off by default so app.py stays quiet.
        step:     When True (with verbose), pause for Enter before each step
                  so a presenter can narrate over a live run.

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    log, pause = _make_logger(verbose, step)
    log(f"\n=== FitFindr run ===\nUser query: {query!r}")

    # Step 1: fresh session for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into description / size / max_price.
    pause("parse the query")
    log("\n[1] Parsing the query with the LLM…")
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]
    log(f"    parsed → {session['parsed']}")

    # No usable description → stop early, don't search on nothing.
    if not description:
        session["error"] = (
            "Tell me what you're looking for — try describing the item, "
            "like 'vintage graphic tee under $30'."
        )
        log("    ✗ no usable description → set session['error'] and stop "
            "(no tools called)")
        log(f"    error: {session['error']}")
        return session

    # Step 3: search. This is the branch that decides whether we continue.
    pause("call search_listings")
    log(f"\n[2] search_listings({description!r}, size={size!r}, "
        f"max_price={max_price!r})")
    session["search_results"] = search_listings(description, size, max_price)
    log(f"    → {len(session['search_results'])} listing(s) matched")
    if not session["search_results"]:
        bits = [f"\"{description}\""]
        if size:
            bits.append(f"size {size}")
        if max_price is not None:
            bits.append(f"under ${max_price:g}")
        session["error"] = (
            f"No listings matched {', '.join(bits)}. "
            "Try raising your price, dropping the size, or different keywords."
        )
        log("    ✗ 0 results → set session['error'] and stop BEFORE "
            "suggest_outfit")
        log(f"    error: {session['error']}")
        return session  # do NOT call suggest_outfit with empty input

    # Step 4: pick the top match as the item to work with.
    session["selected_item"] = session["search_results"][0]
    log(f"    selected_item = search_results[0]: "
        f"{session['selected_item']['title']!r} (${session['selected_item']['price']:g})")

    # Step 5: style the selected item against the wardrobe.
    pause("call suggest_outfit")
    log("\n[3] suggest_outfit(selected_item, wardrobe)")
    log("    passing the SAME selected_item dict from search — no re-entry")
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], wardrobe
    )
    # State-passing proof: the item handed to the tool is the exact search result.
    log(f"    state check: session['selected_item'] is search_results[0] → "
        f"{session['selected_item'] is session['search_results'][0]}")
    log(f"    → outfit_suggestion: {session['outfit_suggestion']}")

    # Step 6: turn the outfit into a shareable caption.
    pause("call create_fit_card")
    log("\n[4] create_fit_card(outfit_suggestion, selected_item)")
    log("    passing the outfit_suggestion string straight through — no re-entry")
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )
    log(f"    → fit_card: {session['fit_card']}")

    # Step 7: done.
    log("\n[done] session filled: selected_item, outfit_suggestion, fit_card; "
        "error=None")
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    parser = argparse.ArgumentParser(
        description="Run the FitFindr agent with step-by-step logging."
    )
    parser.add_argument(
        "query", nargs="?",
        help="natural-language request; omit to run the two built-in demo scenarios",
    )
    parser.add_argument(
        "--step", action="store_true",
        help="pause for Enter before each step (good for narrating a live demo)",
    )
    parser.add_argument(
        "--empty-wardrobe", action="store_true",
        help="use an empty wardrobe (triggers suggest_outfit's general-advice path)",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="turn off the step-by-step logging",
    )
    args = parser.parse_args()

    verbose = not args.quiet
    wardrobe = get_empty_wardrobe() if args.empty_wardrobe else get_example_wardrobe()

    if args.query:
        run_agent(args.query, wardrobe, verbose=verbose, step=args.step)
    else:
        # Built-in demo: a complete happy path, then the no-results failure path.
        print("########## SCENARIO 1: complete interaction (all 3 tools) ##########")
        run_agent(
            "looking for a vintage graphic tee under $30",
            get_example_wardrobe(), verbose=verbose, step=args.step,
        )
        print("\n\n########## SCENARIO 2: triggered failure (no results) ##########")
        run_agent(
            "designer ballgown size XXS under $5",
            get_example_wardrobe(), verbose=verbose, step=args.step,
        )
