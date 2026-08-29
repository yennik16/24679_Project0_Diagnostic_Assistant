"""
Run this in Colab. It builds a single self-contained HTML file (plain
HTML/CSS/JavaScript - no ipywidgets, no Python backend at runtime) and
downloads it to your computer. Double-click the downloaded file and it
opens as its own real browser window/tab, completely separate from Colab.

Why this instead of the ipywidgets version:
  - ipywidgets with dynamically-created widgets is known to be unreliable
    in Colab specifically (buttons made inside a click handler often need
    an extra click, or don't register at all) - that's almost certainly
    the cause of the "needs two clicks" issue.
  - Colab renders cell output inside a sandboxed iframe, which generally
    blocks window.open(), so there's no reliable way to pop a real window
    open *from* a Colab cell.
  - This sidesteps both: the app itself is a normal downloaded HTML file,
    opened normally by your OS/browser, with plain JS handling every
    click directly (no comm channel, no lag, no double-click behavior).

The Live PID Reference data is fetched from OBDb ONCE, here in Colab
(which does have working internet access), and embedded directly into the
HTML file - so the popup never needs to make its own network call and can
never fail to display it silently.

To check a different vehicle's PIDs, just rerun this cell with new inputs.
"""

import re
import json
import difflib
import urllib.request
import urllib.error

try:
    from obd_database import OBD_CODES as OBD_DATABASE, KNOWN_MODELS
except ImportError:
    OBD_DATABASE = {}
    KNOWN_MODELS = []

# ============================================================
# OBDb integration (same logic as the notebook version)
# ============================================================

OBDB_RAW_BASE = "https://raw.githubusercontent.com/OBDb/{repo}/main/signalsets/v3/default.json"
OBDB_API_REPOS = "https://api.github.com/orgs/OBDb/repos"
_obdb_repo_list_cache = None


class OBDbNetworkError(Exception):
    pass


def _http_get_text(url, timeout=5, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": "diagnostic-assistant"}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _probe_repo(repo, timeout=4):
    """True/False for exists/not-found. Raises OBDbNetworkError for an
    actual connectivity failure (as opposed to a normal 404), so callers
    can stop burning time retrying candidates once the network is down."""
    url = OBDB_RAW_BASE.format(repo=repo)
    req = urllib.request.Request(url, headers={"User-Agent": "diagnostic-assistant"}, method="HEAD")
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise OBDbNetworkError(f"HTTP {e.code} from GitHub")
    except Exception as e:
        raise OBDbNetworkError(str(e))


def _list_obdb_repos():
    global _obdb_repo_list_cache
    if _obdb_repo_list_cache is not None:
        return _obdb_repo_list_cache
    names, page = [], 1
    try:
        while True:
            data = json.loads(_http_get_text(f"{OBDB_API_REPOS}?per_page=100&page={page}"))
            if not data or isinstance(data, dict):
                break
            names.extend(r["name"] for r in data)
            if len(data) < 100:
                break
            page += 1
    except Exception:
        pass
    _obdb_repo_list_cache = names
    return names


def find_obdb_repo(make, model):
    make, model = make.strip(), model.strip()
    candidates = []
    if model:
        candidates.append(f"{make}-{model}".replace(" ", "-"))
        candidates.append(f"{make}-{re.sub(r'([A-Za-z])(\d)', r'\1-\2', model)}".replace(" ", "-"))
    candidates.append(make.replace(" ", "-"))

    seen = set()
    for repo in candidates:
        if repo in seen:
            continue
        seen.add(repo)
        if _probe_repo(repo):  # may raise OBDbNetworkError - let it propagate
            return repo

    all_repos = _list_obdb_repos()
    if all_repos:
        target = f"{make}-{model}".replace(" ", "-") if model else make
        best = difflib.get_close_matches(target, all_repos, n=1, cutoff=0.5)
        if best:
            return best[0]
    return None


def parse_signalset(raw_json_text):
    data = json.loads(raw_json_text)
    signals = {}
    for cmd in data.get("commands", []):
        header = cmd.get("hdr", "?")
        pid = cmd.get("cmd", {})
        for sig in cmd.get("signals", []):
            signals[sig["id"]] = {
                "name": sig.get("name", sig["id"]),
                "unit": sig.get("fmt", {}).get("unit", ""),
                "header": header,
                "pid": pid,
            }
    return signals


def fetch_obdb_signalset(make, model):
    """Returns (signals_dict_or_None, repo_name_or_None). Raises
    OBDbNetworkError if GitHub is unreachable at all."""
    repo = find_obdb_repo(make, model)
    if not repo:
        return None, None
    raw = _http_get_text(OBDB_RAW_BASE.format(repo=repo))
    return parse_signalset(raw), repo


# ============================================================
# Decision tree
# ============================================================

DIAGNOSTIC_TREE = {
    "Engine": {
        "question": "What is the primary engine symptom?",
        "options": {
            "Performance Issue": {
                "question": "When does it happen?",
                "options": {
                    "Hesitation/Stumbling": {
                        "diagnosis": "Potential Fuel or Air Delivery Issue",
                        "tests": [
                            {
                                "check": "Fuel Pressure",
                                "instruction": "Connect a pressure gauge to the fuel rail. Is pressure within spec?",
                                "options": {
                                    "Yes": {
                                        "question": "Pressure OK. Let's check injectors. Do you hear a clicking sound from each injector using a screwdriver as a stethoscope?",
                                        "options": {
                                            "Yes": "Injectors are firing. Check for electrical pulse with a noid light.",
                                            "No": "Injector failure. Replace the non-clicking injector."
                                        }
                                    },
                                    "No": "Replace fuel pump or filter."
                                }
                            },
                            {
                                "check": "MAF Sensor",
                                "instruction": "Unplug the MAF sensor. Does the car idle better?",
                                "options": {
                                    "Yes": "MAF sensor is faulty or dirty.",
                                    "No": "MAF is likely OK. Check for vacuum leaks."
                                }
                            }
                        ]
                    },
                    "Overheating": {
                        "diagnosis": "Cooling System Failure",
                        "tests": [
                            {"check": "Coolant Level", "instruction": "Check reservoir and radiator (when cold). Is it full?", "options": {"Yes": "Check thermostat or fan.", "No": "Inspect for external leaks or head gasket issues."}}
                        ]
                    }
                }
            }
        }
    }
}


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Automotive Diagnostic Assistant</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background:#ffffff; color:#212529;
         max-width:820px; margin:24px auto; padding:0 16px; }
  h2, h3 { color:#212529; }
  .box { padding:12px; border-radius:4px; margin:10px 0; border-left:6px solid #adb5bd;
         background:#f8f9fa; font-size:14px; line-height:1.5; }
  .box.success { background:#d4edda; border-color:#28a745; color:#155724; }
  .box.danger  { background:#f8d7da; border-color:#dc3545; color:#721c24; }
  .box.warning { background:#fff3cd; border-color:#e0a800; color:#664d03; }
  .box.neutral { background:#f1f3f5; border-color:#adb5bd; color:#212529; }
  .btnrow { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; align-items:center; }
  .btn { padding:9px 16px; border:none; border-radius:4px; cursor:pointer; font-size:14px;
         background:#6c757d; color:#ffffff; }
  .btn:hover { opacity:0.85; }
  .btn-info { background:#17a2b8; }
  .btn-warning { background:#ffc107; color:#212529; }
  .btn-primary { background:#0d6efd; }
  .btn-success { background:#28a745; }
  .text-input { padding:9px; border:1px solid #ced4da; border-radius:4px; font-size:14px; min-width:220px; }
  .testbox { border:1px solid #dee2e6; border-radius:4px; padding:12px; margin:10px 0; background:#ffffff; }
  .pidnote { font-size:0.85em; color:#495057; margin-top:6px; }
  .search-link { display:inline-block; background:#4285f4; color:#ffffff !important; padding:9px 14px;
                 border-radius:4px; text-decoration:none; margin:8px 8px 8px 0; }
  .table-wrap { max-height:340px; overflow:auto; border:1px solid #dee2e6; border-radius:4px; margin-top:8px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th, td { padding:6px 8px; text-align:left; border-bottom:1px solid #eee; }
  th { background:#f1f3f5; position:sticky; top:0; }
</style>
</head>
<body>
<h2>Professional Diagnostic Assistant</h2>
<div id="screen"></div>

<script>
const DATA = __DATA_JSON__;

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function clearScreen() {
  const el = document.getElementById('screen');
  el.innerHTML = '';
  return el;
}

function similarity(a, b) {
  const wa = new Set(a.toLowerCase().split(/\W+/).filter(Boolean));
  const wb = new Set(b.toLowerCase().split(/\W+/).filter(Boolean));
  if (wa.size === 0 || wb.size === 0) return 0;
  let common = 0;
  wa.forEach(w => { if (wb.has(w)) common++; });
  return common / Math.max(wa.size, wb.size);
}

function matchPidForCheck(checkText) {
  const signals = DATA.pid_signals || {};
  const ids = Object.keys(signals);
  if (ids.length === 0) return null;
  let best = null, bestScore = 0;
  ids.forEach(id => {
    const score = similarity(checkText, signals[id].name);
    if (score > bestScore) { bestScore = score; best = id; }
  });
  if (bestScore < 0.34) return null;
  const info = signals[best];
  return `Live PID match: <b>${escapeHtml(info.name)}</b> - cmd ${escapeHtml(JSON.stringify(info.pid))} @ header ${escapeHtml(info.header)} (${escapeHtml(info.unit)})`;
}

function appendSearchHelper(el, resultText) {
  const query = encodeURIComponent(`${DATA.vehicle.year} ${DATA.vehicle.make} ${DATA.vehicle.model} ${resultText}`);
  const link = document.createElement('a');
  link.href = `https://www.google.com/search?q=${query}`;
  link.target = '_blank';
  link.className = 'search-link';
  link.textContent = 'Repair Guide Search \u{1F50D}';
  el.appendChild(link);

  const restart = document.createElement('button');
  restart.className = 'btn btn-success';
  restart.textContent = 'Start New Triage';
  restart.addEventListener('click', showInitialPrompt);
  el.appendChild(restart);
}

function renderNode(node) {
  if (typeof node === 'string') { renderConclusion(node); return; }
  if (node.tests) { renderTests(node); return; }
  renderQuestion(node);
}

function renderQuestion(node) {
  const el = clearScreen();
  const q = document.createElement('div');
  q.className = 'box neutral';
  q.innerHTML = `<b>${escapeHtml(node.question || 'Select an option:')}</b>`;
  el.appendChild(q);

  const row = document.createElement('div');
  row.className = 'btnrow';
  const options = node.options || node;
  Object.entries(options).forEach(([opt, child]) => {
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = opt;
    btn.addEventListener('click', () => renderNode(child));
    row.appendChild(btn);
  });
  el.appendChild(row);
}

function renderTests(node) {
  const el = clearScreen();
  const title = document.createElement('h3');
  title.style.color = '#0d6efd';
  title.textContent = 'Diagnosis Stage: ' + (node.diagnosis || 'Step');
  el.appendChild(title);

  node.tests.forEach(test => {
    const box = document.createElement('div');
    box.className = 'testbox';
    const pidNote = matchPidForCheck(test.check);
    box.innerHTML = `<b>${escapeHtml(test.check)}</b>: ${escapeHtml(test.instruction)}` +
      (pidNote ? `<div class="pidnote">${pidNote}</div>` : '');

    const row = document.createElement('div');
    row.className = 'btnrow';
    Object.entries(test.options).forEach(([opt, result]) => {
      const btn = document.createElement('button');
      btn.className = 'btn btn-info';
      btn.textContent = opt;
      btn.addEventListener('click', () => renderNode(result));
      row.appendChild(btn);
    });
    box.appendChild(row);
    el.appendChild(box);
  });
}

function renderConclusion(text) {
  const el = clearScreen();
  const box = document.createElement('div');
  box.className = 'box success';
  box.textContent = text;
  el.appendChild(box);
  appendSearchHelper(el, text);
}

function lookupCode(rawCode) {
  const code = (rawCode || '').toUpperCase().trim();
  const res = DATA.obd_database[code];
  const el = clearScreen();
  if (res) {
    const box = document.createElement('div');
    box.className = 'box success';
    box.innerHTML = `<b>${escapeHtml(code)}:</b> ${escapeHtml(res.desc)}`;
    el.appendChild(box);
    appendSearchHelper(el, `${code} ${res.desc}`);
  } else {
    const box = document.createElement('div');
    box.className = 'box danger';
    box.textContent = 'Code not found. Describe the symptoms instead below.';
    el.appendChild(box);
    renderSymptomPromptInto(el);
  }
}

function renderSymptomPromptInto(el) {
  const label = document.createElement('div');
  label.innerHTML = '<b>Describe the issue:</b>';
  el.appendChild(label);

  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'e.g., car stumbles';
  input.className = 'text-input';
  el.appendChild(input);

  const btn = document.createElement('button');
  btn.className = 'btn btn-primary';
  btn.textContent = 'Analyze';
  btn.addEventListener('click', () => analyzeSymptoms(input.value));
  el.appendChild(btn);

  input.addEventListener('keydown', e => { if (e.key === 'Enter') analyzeSymptoms(input.value); });
  input.focus();
}

function renderSymptomPrompt() {
  renderSymptomPromptInto(clearScreen());
}

function analyzeSymptoms(rawText) {
  const text = (rawText || '').toLowerCase();
  let node;
  if (['stumble', 'hesitat', 'gas', 'stall'].some(k => text.includes(k))) {
    node = DATA.diagnostic_tree.Engine.options['Performance Issue'].options['Hesitation/Stumbling'];
  } else if (['overheat', 'hot', 'temperature'].some(k => text.includes(k))) {
    node = DATA.diagnostic_tree.Engine.options['Performance Issue'].options['Overheating'];
  } else {
    node = DATA.diagnostic_tree;
  }
  renderNode(node);
}

function showPidReference() {
  const el = clearScreen();
  const heading = document.createElement('h3');
  heading.textContent = `Diagnostic for ${DATA.vehicle.year} ${DATA.vehicle.make} ${DATA.vehicle.model}`;
  el.appendChild(heading);

  const signals = DATA.pid_signals || {};
  const ids = Object.keys(signals);

  if (ids.length === 0) {
    const box = document.createElement('div');
    box.className = 'box warning';
    box.innerHTML = `No OBDb repository was found for '<b>${escapeHtml(DATA.vehicle.make)} ${escapeHtml(DATA.vehicle.model)}</b>' when this file was generated. Coverage is community-contributed, so older or less common vehicles often aren't in there yet. Browse <a href="https://github.com/OBDb" target="_blank">github.com/OBDb</a> to check, or rerun the Colab cell after requesting the repo.`;
    el.appendChild(box);
  } else {
    const summary = document.createElement('div');
    summary.className = 'box success';
    summary.innerHTML = `Loaded <b>${ids.length}</b> signals from OBDb repo <a href="https://github.com/OBDb/${escapeHtml(DATA.pid_repo)}" target="_blank">${escapeHtml(DATA.pid_repo)}</a> (embedded when this file was generated). These are live PIDs for a real scan tool/ELM327 adapter - matching test steps in the decision tree show the exact PID to query.`;
    el.appendChild(summary);

    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    let rows = '';
    ids.slice(0, 200).forEach(id => {
      const s = signals[id];
      rows += `<tr><td>${escapeHtml(s.name)}</td><td>${escapeHtml(id)}</td><td>${escapeHtml(s.header)}</td><td>${escapeHtml(JSON.stringify(s.pid))}</td><td>${escapeHtml(s.unit)}</td></tr>`;
    });
    wrap.innerHTML = `<table><tr><th>Signal</th><th>ID</th><th>Header</th><th>Cmd</th><th>Unit</th></tr>${rows}</table>`;
    el.appendChild(wrap);
  }

  const back = document.createElement('button');
  back.className = 'btn btn-success';
  back.textContent = 'Back';
  back.addEventListener('click', showInitialPrompt);
  el.appendChild(back);
}

function showInitialPrompt() {
  const el = clearScreen();
  const heading = document.createElement('h3');
  heading.textContent = `Diagnostic for ${DATA.vehicle.year} ${DATA.vehicle.make} ${DATA.vehicle.model}`;
  el.appendChild(heading);

  const prompt = document.createElement('div');
  prompt.innerHTML = "<b>Do you have a code, want to describe the issue, or look up this vehicle's live sensor PIDs?</b>";
  el.appendChild(prompt);

  const row = document.createElement('div');
  row.className = 'btnrow';

  const codeInput = document.createElement('input');
  codeInput.type = 'text';
  codeInput.placeholder = 'Enter OBD-II Code';
  codeInput.className = 'text-input';
  row.appendChild(codeInput);

  const lookupBtn = document.createElement('button');
  lookupBtn.className = 'btn btn-info';
  lookupBtn.textContent = 'Lookup Code';
  lookupBtn.addEventListener('click', () => lookupCode(codeInput.value));
  row.appendChild(lookupBtn);
  codeInput.addEventListener('keydown', e => { if (e.key === 'Enter') lookupCode(codeInput.value); });

  const descBtn = document.createElement('button');
  descBtn.className = 'btn btn-warning';
  descBtn.textContent = 'Describe Symptoms';
  descBtn.addEventListener('click', renderSymptomPrompt);
  row.appendChild(descBtn);

  const pidBtn = document.createElement('button');
  pidBtn.className = 'btn';
  pidBtn.textContent = 'Live PID Reference (OBDb)';
  pidBtn.addEventListener('click', showPidReference);
  row.appendChild(pidBtn);

  el.appendChild(row);
}

showInitialPrompt();
</script>
</body>
</html>
"""


def build_app(make, model, year, filename="diagnostic_assistant.html"):
    print(f"Looking up OBDb data for {year} {make} {model} ...")
    try:
        signals, repo = fetch_obdb_signalset(make, model)
    except OBDbNetworkError as e:
        print(f"Couldn't reach GitHub ({e}). Live PID Reference will show as unavailable in the app; "
              f"everything else still works.")
        signals, repo = None, None

    if signals:
        print(f"Found {len(signals)} signals in OBDb repo '{repo}'.")
    else:
        print("No OBDb repo found for this vehicle - Live PID Reference will show as unavailable.")

    data = {
        "vehicle": {"make": make, "model": model, "year": year},
        "obd_database": OBD_DATABASE,
        "diagnostic_tree": DIAGNOSTIC_TREE,
        "pid_signals": signals or {},
        "pid_repo": repo,
    }
    html = HTML_TEMPLATE.replace("__DATA_JSON__", json.dumps(data))
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved {filename}")
    return filename


if __name__ == "__main__":
    make = input("Vehicle make (e.g. Toyota): ").strip()
    model = input("Vehicle model (e.g. Camry): ").strip()
    year = input("Vehicle year (e.g. 2015): ").strip()

    fname = build_app(make, model, year)

    try:
        from google.colab import files
        files.download(fname)
        print("Download started - open the file once it lands in your Downloads folder.")
    except ImportError:
        print(f"Not running in Colab - open {fname} directly in your browser.")
