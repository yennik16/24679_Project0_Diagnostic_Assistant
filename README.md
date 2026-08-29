# Automotive Diagnostic Assistant

A self-guided car troubleshooting tool. It looks up OBD-II trouble codes,
walks you through a test-driven decision tree from a plain-English symptom
description, and (when available) shows the real live-sensor PID a scan
tool would use to verify each test step, pulled from the community
[OBDb](https://github.com/OBDb) project.

## What it does

- **Trouble code lookup** - enter a code (e.g. `P0300`) and get its
  description and likely causes from a local database.
- **Symptom-driven diagnosis** - describe a problem in your own words
  ("car stumbles and hesitates") and it routes you into a branching
  sequence of concrete tests. Each answer narrows things down until it
  reaches a specific root cause and fix - not just a list of possibilities.
- **Live PID reference** - for the vehicle the app was generated for, it
  shows the actual OBD-II command and decoding formula for relevant
  sensors, matched automatically against the test steps in the decision
  tree, so a step like "check fuel pressure" can point at the real PID a
  scan tool would query.

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

**Regenerate it for a different vehicle:**
```bash
python3 build_diagnostic_app.py
```
This prompts for make/model/year, fetches that vehicle's OBDb data if
available, and writes a new `index.html`. In Google Colab, running the
same script also triggers a normal file download of the result.

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
