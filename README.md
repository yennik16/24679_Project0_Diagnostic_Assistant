# Automotive Diagnostic Assistant

A self-guided car troubleshooting tool. It looks up OBD-II trouble codes,
walks you through a test-driven decision tree from a plain-English symptom
description, and (when available) shows the real live-sensor PID a scan
tool would use to verify each test step, pulled from the community
[OBDb](https://github.com/OBDb) project.

## What it does

- **Vehicle selection, in the app** - on load (or via "Change Vehicle"),
  enter a make/model/year and the app fetches that vehicle's live-PID
  data directly from OBDb using the browser's own `fetch()` - no need to
  regenerate the file for a different vehicle. This requires the page to
  be hosted over http/https (e.g. GitHub Pages); if opened as a local
  file, browsers block that fetch, so the app says so and continues
  without live PID data - trouble code lookup and the decision tree still
  work fully offline either way.
- **Trouble code lookup** - enter a code (e.g. `P0300`) and get its
  description and likely causes from a local database.
- **Symptom-driven diagnosis with confidence-ranked classification** -
  describe a problem in your own words ("the engine hesitates and
  stumbles when I accelerate") and the app classifies it against 16
  known symptom categories using **TF-IDF vectorization and cosine
  similarity** (see "How the symptom classifier works" below), showing
  the top 2-3 candidates with confidence percentages rather than
  silently guessing one. Picking a match routes you into a multi-level
  sequence of concrete tests (several branches go 4-5 questions deep);
  each answer narrows things down until it reaches a specific root cause
  and fix. Covers engine starting issues, four performance-issue
  categories, brakes, steering, and electrical faults.
- **Live PID reference** - shows the actual OBD-II command and decoding
  formula for the loaded vehicle's sensors, matched automatically against
  test steps in the decision tree (e.g. a "Battery Voltage" test step
  shows the exact PID a scan tool would query).

## How the symptom classifier works

This is the project's non-trivial computational piece, so it's worth
spelling out. Naively checking whether the input string *contains* a
fixed keyword ("does the text include 'overheat'?") is trivial rule
matching and breaks the moment someone phrases things differently. This
app instead does real text classification:

1. Each of the 16 symptom categories has 5-6 hand-written example phrases
   (its "training documents") - e.g. Overheating includes phrases like
   "temperature gauge climbs into the red" and "steam coming from under
   the hood".
2. At startup, the app builds a **TF-IDF** (term frequency - inverse
   document frequency) model over these documents: common words that
   appear in most categories (like "car" or "when") are automatically
   down-weighted, while distinctive words that concentrate in one
   category are up-weighted - computed, not hand-tuned.
3. The user's free-text description is run through the same
   vectorization and compared against every category's vector using
   **cosine similarity**.
4. The categories are ranked by similarity and shown with a normalized
   confidence percentage, so the user (not a hard-coded if/else chain)
   makes the final call when it's ambiguous - e.g. "brake pedal feels
   soft and mushy" correctly ranks *Spongy/Soft Brake Pedal* well above
   *Brake Pedal Pulsates* or *Goes to the Floor*, despite none of those
   category labels containing the words "soft" or "mushy" verbatim.

This is implemented from scratch in vanilla JavaScript (no ML library)
in the `SYMPTOM_CATEGORIES` / `buildClassifier` / `cosineSimilarity`
functions in `index.html`.

## Known limitations

- The symptom classifier's vocabulary is limited to its 16 categories'
  example phrases; a symptom described in very unfamiliar terms may
  score low across the board (it then falls back to manual category
  browsing rather than forcing a bad guess).
- PID-to-test matching (a separate, simpler feature from the symptom
  classifier above) is word-overlap based, not semantic - it can produce
  a loose match when two unrelated checks share a generic word (e.g.
  "Coolant Level" vs. "Fuel Level" both contain "Level").
- The decision tree's questions and the trouble-code database are still
  hand-authored rules, not learned from data - the symptom *classifier*
  that routes into that tree is the learned/computed part.

## How it's organized

```
.
├── index.html               <- the app itself. Open this in a browser.
├── build_diagnostic_app.py  <- (re)generates index.html for a given vehicle
├── obd_database.py          <- local trouble-code database
└── README.md
```

`index.html` is a single self-contained file (HTML/CSS/JavaScript, no
external libraries, no build step). All vehicle-specific data - the
trouble code table and that vehicle's live PID signals - is embedded
directly in the file at generation time, so it has no server and no
runtime network dependency; it runs from a plain double-click.

## Dependencies

None to *run* the app - any modern browser (Chrome, Firefox, Edge, Safari)
opens `index.html` directly.

To *regenerate* `index.html` for a different vehicle, you need Python 3
(standard library only - `json`, `re`, `difflib`, `urllib` - no `pip
install` required) and an internet connection (to query the OBDb project
for that vehicle's live PID data; if none is found, the generated app
still works, it just shows "no live PID data available" for that vehicle).

## How to run it

**Just view/use the app:** download this repository (or just `index.html`)
and open `index.html` directly in a browser. Note: some file previewers
(Google Drive's preview pane, some in-browser "quick look" tools) don't
execute JavaScript and will appear to load forever - make sure you're
opening it in an actual browser window, not a preview pane.

**Regenerate `index.html`** (only needed if you want to pre-bake a default
vehicle for an offline demo - vehicle selection otherwise happens inside
the app itself):
```bash
python3 build_diagnostic_app.py
```
Leave the make/model/year prompts blank to get an app that opens straight
to its own vehicle-selection screen (this is what's included here). In
Google Colab, running the same script also triggers a normal file
download of the result.

## AI tool use

Claude (Anthropic) was used throughout this project's development:
- Debugging an `AttributeError` crash in an earlier ipywidgets-based
  prototype, and redesigning the decision-tree traversal logic to fix it.
- Researching the OBDb project's structure/licensing and writing the
  integration that fetches and parses its live-PID signal data.
- Diagnosing reliability issues specific to running ipywidgets in Google
  Colab (unreliable dynamically-created widgets, sandboxed output iframes
  blocking `window.open()`), which led to converting the tool from an
  ipywidgets notebook UI into this standalone HTML/JS application.
- Implementing the TF-IDF/cosine-similarity symptom classifier described
  above, in response to feedback that keyword-substring matching was too
  trivial a form of "intelligence" for the assignment's rubric.
- Drafting this README.

All prompts, iterations, and design decisions were reviewed and directed
by the author throughout.
