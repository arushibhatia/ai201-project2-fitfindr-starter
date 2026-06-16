# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

## Running it

```bash
python app.py        # launches the Gradio UI (open the URL it prints)
python agent.py      # runs a complete interaction and a no-results failure, logging each step
pytest tests/        # runs the tool tests (use `pytest -s tests/` to see output)
```

`agent.py` logs what the agent does at each step, which is handy for the demo. A few options:

```bash
python agent.py                                   # the two built-in demo scenarios
python agent.py "vintage graphic tee under \$30"  # run your own query
python agent.py "vintage graphic tee" --step      # pause before each step so you can narrate
python agent.py "vintage graphic tee" --empty-wardrobe  # trigger the general-advice fallback
```

The log prints the parsed query, the search result count, the selected item, each tool call, and a `state check` line confirming the item handed to `suggest_outfit` is the exact object returned by `search_listings` — useful for the "state passing between tools" part of the demo.

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings` | `description` (str), `size` (str or None), `max_price` (float or None) | `list[dict]`: matching listings, best match first, or an empty list if nothing matches | Filters the listings dataset by size and price, then ranks what's left by how well it matches the description. |
| `suggest_outfit` | `new_item` (dict), `wardrobe` (dict) | `str`: an outfit suggestion, never empty | Asks the LLM to style the found item using pieces from the wardrobe, or gives general advice if the wardrobe is empty. |
| `create_fit_card` | `outfit` (str), `new_item` (dict) | `str`: a short caption, or an error message if the outfit is blank | Turns the outfit suggestion into a casual 2-4 sentence caption that mentions the item, price, and platform. |

Some detail on the inputs and outputs:

- Each dict returned by `search_listings` is a full listing with these fields: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Size is matched loosely and case-insensitively, so "M" still matches "S/M" or "M/L", and `max_price` is an inclusive ceiling.
- `new_item` is one of those listing dicts, usually `search_results[0]`.
- `wardrobe` follows `data/wardrobe_schema.json`: an `items` list where each item has `id`, `name`, `category`, `colors`, `style_tags`, and an optional `notes`. An empty wardrobe is `{"items": []}`.
- `suggest_outfit` and `create_fit_card` both call Groq's `llama-3.3-70b-versatile` at temperature 0.7, which is high enough that the same input gives different captions but still reads coherently.

## How the Planning Loop Works

`run_agent` in `agent.py` keeps one session dict and decides each step by checking what's already in it, so it doesn't run all three tools every time.

1. Parse the query. The LLM pulls `description`, `size`, and `max_price` out of the raw query as JSON. If there's no usable description, the agent sets `session["error"]` and returns right away without calling any tools.
2. Search. It calls `search_listings(description, size, max_price)` and stores the result in `session["search_results"]`. If the list is empty, it sets a `session["error"]` message and returns before calling `suggest_outfit`. If the list has matches, it stores `search_results[0]` as `session["selected_item"]` and keeps going.
3. Suggest an outfit. It calls `suggest_outfit(selected_item, wardrobe)` and stores the result in `session["outfit_suggestion"]`.
4. Create the fit card. It calls `create_fit_card(outfit_suggestion, selected_item)` and stores the result in `session["fit_card"]`.
5. Return the session, which ends with either `fit_card` set (success) or `error` set (stopped early at step 1 or 2).

So a query with no matches stops after the search and never reaches the styling tools, while a query that finds something runs all the way to a fit card.

## Example Walkthrough

Here's a full interaction for the query: "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

1. The LLM parses the query into `description="vintage graphic tee"`, `size=None`, and `max_price=30.0`, saved to `session["parsed"]`. The loop calls `search_listings("vintage graphic tee", None, 30.0)`, which returns matching listings best-first, and stores the top one as `session["selected_item"]` (say, a $24 bootleg-style graphic tee from Depop).
2. The loop calls `suggest_outfit(selected_item, wardrobe)` with the example wardrobe and saves the result to `session["outfit_suggestion"]`. The user never retypes the item; it comes straight from `selected_item`. The result is something like: "Wear the bootleg graphic tee with your baggy dark-wash jeans and chunky white sneakers, tuck the front hem, and throw the black denim jacket over it when it cools off. Easy, lived-in 90s streetwear look."
3. The loop calls `create_fit_card(outfit_suggestion, selected_item)` and saves the caption to `session["fit_card"]`, for example: "found this $24 bootleg graphic tee on depop and it's already my whole personality 🖤 baggy jeans + chunky sneakers, denim jacket on standby. thrift wins only"

Finally `run_agent` returns the session, and `app.py` fills the three panels: the top listing, the outfit idea from step 2, and the fit card from step 3. If `search_listings` had returned nothing, step 1 would set `session["error"]` instead and the user would see that message.

## State Management

Everything for a run lives in one session dict, created by `_new_session`. The tools don't call each other. Each one's output gets written to the session under its own key, and the next step reads it from there:

- `query`: the raw user string
- `parsed`: `{description, size, max_price}` from the parse step
- `search_results`: the list from `search_listings`
- `selected_item`: the top match, `search_results[0]`
- `wardrobe`: the wardrobe dict passed in at the start
- `outfit_suggestion`: the string from `suggest_outfit`
- `fit_card`: the string from `create_fit_card`
- `error`: `None` normally, or a message if the run stopped early

The data is passed by reference, not re-entered. `search_listings` writes `search_results`, the loop copies `search_results[0]` into `selected_item`, and that same object goes into `suggest_outfit`. Its output becomes `outfit_suggestion`, which goes straight into `create_fit_card`. At the end, `app.py` reads `selected_item`, `outfit_suggestion`, `fit_card`, and `error` from the session to fill the three UI panels.

## Error Handling

Each tool handles its own failure mode, and none of them crash the agent.

| Tool | Failure mode | What happens |
|------|--------------|--------------|
| `search_listings` | No listings match | Returns an empty list instead of raising. The loop sees the empty list, sets `session["error"]`, and stops before calling `suggest_outfit`. |
| `suggest_outfit` | Wardrobe is empty | Switches to general styling advice instead of naming owned pieces, so it still returns a useful non-empty string. |
| `create_fit_card` | Outfit is missing or blank | Returns a clear error message string without calling the LLM. |

Examples from testing:

- No results: `search_listings("designer ballgown", "XXS", 5)` returns `[]`. The full agent then sets `session["error"]` to `No listings matched "designer ballgown", size XXS, under $5. Try raising your price, dropping the size, or different keywords.` and leaves `session["fit_card"]` as `None`. `suggest_outfit` was never called on this path.
- Empty wardrobe: `suggest_outfit(item, get_empty_wardrobe())` returns general advice like "This graphic tee is perfect for a laid-back, grunge-inspired look. You can pair it with distressed denim, skirts, or even shorts..." with no made-up owned pieces and no exception.
- Blank outfit: `create_fit_card("", item)` returns "Can't make a fit card yet, there's no outfit to caption. Find an item and get a styling suggestion first." instead of raising or calling the LLM.

## Spec Reflection

One way the spec helped: it fixed the three function signatures and gave a worked example up front. Because I designed each tool in `planning.md` against those signatures before writing code, the empty-results path and the state hand-off were already decided on paper, so building it was mostly filling in contracts I'd already defined.

One way the implementation diverged: the spec said `search_listings` returns matches "sorted by relevance" but never defined relevance, so I had to decide that myself. I ranked by the number of distinct description keywords found across each listing's text fields, broke ties by total mentions, ignored filler words, and dropped listings with no overlap. None of that was in the spec; it was what I needed to get sensible, stable ordering.

## AI Usage

I used Claude for the implementation, giving it one `planning.md` section at a time and checking the output against my spec before keeping it.

- `search_listings`: I gave Claude the Tool 1 block from `planning.md` (inputs, return value, loose size matching, empty-list failure mode) and told it to use `load_listings()` instead of re-reading the file. It worked, but its first version ranked results by raw word count, so I changed the scoring to count distinct description words with total mentions as the tie-break and to drop listings with no overlap. Then I ran the three pytest cases (results found, empty results, price filter) to confirm they passed.
- Planning loop (`run_agent`): I gave Claude the architecture diagram along with the Planning Loop and State Management sections. Its first version called all three tools in sequence, so I changed it to branch on the search result, setting `session["error"]` and returning early on an empty list so `suggest_outfit` never runs without input. I checked both paths in `agent.py`: the happy path fills `fit_card`, and the no-results path leaves `fit_card` as `None` with `error` set.
