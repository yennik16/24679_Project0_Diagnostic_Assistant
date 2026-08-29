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
- **Symptom-driven diagnosis** - describe a problem in your own words
  ("car stumbles and hesitates") and it routes you into a multi-level
  sequence of concrete tests (several branches go 4-5 questions deep).
  Each answer narrows things down until it reaches a specific root cause
  and fix - not just a list of possibilities. Covers engine starting
  issues, four performance-issue categories, brakes, steering, and
  electrical faults.
- **Live PID reference** - shows the actual OBD-II command and decoding
  formula for the loaded vehicle's sensors, matched automatically against
  test steps in the decision tree (e.g. a "Battery Voltage" test step
  shows the exact PID a scan tool would query). The matching is a simple
  word-overlap heuristic, so it's occasionally imprecise - see "Known
  limitations" below.

## Known limitations

- PID-to-test matching is word-overlap based, not semantic - it can
  produce a loose match when two unrelated checks share a generic word
  (e.g. "Coolant Level" vs. "Fuel Level" both contain "Level").
- The decision tree and trouble-code database are hand-authored rules,
  not a learned model - see the AI tool use note below for a discussion
  of adding real classification/optimization.

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
- Drafting this README.

All prompts, iterations, and design decisions were reviewed and directed
by the author throughout.
