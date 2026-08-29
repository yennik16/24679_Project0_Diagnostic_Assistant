"""
Run this in Colab (or any Python 3 environment) to build the standalone
diagnostic app.

What's new in this version:
  - Vehicle selection is back, and lives INSIDE the app itself: a "Change
    Vehicle" screen lets you type a make/model/year and the app fetches
    that vehicle's OBDb live-PID data directly from the browser via
    fetch() - no need to regenerate the file through Python anymore.
    (This only works when the page is served over http(s) - e.g. GitHub
    Pages - because browsers block fetch() from a double-clicked local
    file. If you open it as a local file, the rest of the app still
    works fine; only the live PID fetch is skipped, with a clear message
    explaining why.)
  - The decision tree is much deeper: Engine (Starting Issues + four
    Performance Issue branches), Brakes & Steering (Brake Pedal + Steering
    Wheel), and Electrical & Lights (three sub-branches), each walking
    through several rounds of concrete tests before reaching a specific
    root cause - not a one-step guess.
  - You can still optionally pre-bake a default vehicle here in Python
    (handy for an offline demo); leave the prompts blank to skip that and
    have the app open straight to the vehicle-selection screen.
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
# OBDb integration (Python side - only used if you pre-bake a vehicle)
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
        if _probe_repo(repo):
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
    repo = find_obdb_repo(make, model)
    if not repo:
        return None, None
    raw = _http_get_text(OBDB_RAW_BASE.format(repo=repo))
    return parse_signalset(raw), repo


# ============================================================
# Decision tree - Engine, Brakes & Steering, Electrical & Lights
# Each branch is several rounds of concrete tests deep, not a single guess.
# ============================================================

DIAGNOSTIC_TREE = {
    "Engine": {
        "question": "What is the primary engine symptom?",
        "options": {
            "Starting Issues": {
                "question": "Does the engine crank when you turn the key?",
                "options": {
                    "Cranks normally, just won't start": {
                        "question": "Do you smell raw fuel, or does it backfire/sputter while cranking?",
                        "options": {
                            "Yes, floods / smells like fuel": {
                                "diagnosis": "Possible Flooding or Over-Rich Condition",
                                "tests": [{
                                    "check": "Clear-Flood Start",
                                    "instruction": "Hold the throttle fully open and crank for about 10 seconds. Does it start?",
                                    "options": {
                                        "Yes": {
                                            "diagnosis": "Flooding Source Check",
                                            "tests": [{
                                                "check": "Injector Wet-Plug Test",
                                                "instruction": "Remove the spark plug from one cylinder while the engine is still flooded. Does that plug smell heavily of raw fuel or look visibly wet?",
                                                "options": {
                                                    "Yes, wet with fuel": "Stuck-open fuel injector flooding that cylinder. Replace or professionally clean/test the injector.",
                                                    "No, dry/normal": "Over-rich cold-start enrichment, likely from a coolant temperature sensor reading colder than actual. Test the sensor against actual engine temperature and replace it if inaccurate."
                                                }
                                            }]
                                        },
                                        "No": {
                                            "diagnosis": "Fuel/Ignition Cross-Check",
                                            "tests": [{
                                                "check": "Spark Test",
                                                "instruction": "Pull a spark plug, ground it against bare metal on the block, and crank while watching for a blue spark. Do you see one?",
                                                "options": {
                                                    "No": {
                                                        "diagnosis": "Ignition Component Check",
                                                        "tests": [{
                                                            "check": "Coil Resistance Check",
                                                            "instruction": "Using a multimeter, measure the ignition coil's primary resistance and compare to spec. Is it out of spec?",
                                                            "options": {
                                                                "Yes, out of spec": "Failed ignition coil. Replace the coil.",
                                                                "No, in spec": {
                                                                    "diagnosis": "Sensor vs Module Check",
                                                                    "tests": [{
                                                                        "check": "Crank Sensor Signal Test",
                                                                        "instruction": "Using a scan tool or scope, check for a crank position sensor signal while cranking. Is a clean signal present?",
                                                                        "options": {
                                                                            "No signal": "Failed crankshaft position sensor. Replace the sensor.",
                                                                            "Signal present": "Coil and sensor both test fine, so the fault is in the ignition control module. Replace the ignition control module."
                                                                        }
                                                                    }]
                                                                }
                                                            }
                                                        }]
                                                    },
                                                    "Yes": {
                                                        "diagnosis": "Fuel Delivery Check",
                                                        "tests": [{
                                                            "check": "Regulator Vacuum Pinch Test",
                                                            "instruction": "With a fuel pressure gauge connected, briefly pinch off the vacuum line to the fuel pressure regulator while watching the gauge. Does pressure rise noticeably?",
                                                            "options": {
                                                                "Yes, pressure rises": "Fuel pressure regulator's vacuum diaphragm is leaking, letting excess fuel into the intake. Replace the fuel pressure regulator.",
                                                                "No change": "Regulator is fine, so a stuck-open fuel injector is dumping excess fuel. Replace or professionally clean/test the injector."
                                                            }
                                                        }]
                                                    }
                                                }
                                            }]
                                        }
                                    }
                                }]
                            },
                            "No unusual smell/sputter": {
                                "diagnosis": "No-Spark / No-Fuel Diagnosis",
                                "tests": [{
                                    "check": "Spark Test",
                                    "instruction": "Pull a spark plug, ground it to the block, and crank briefly. Do you see spark?",
                                    "options": {
                                        "No": {
                                            "question": "Check the crank position sensor connector and ignition coil connections for corrosion or looseness. Any visible damage?",
                                            "options": {
                                                "Yes, damaged/loose wiring": "Wiring or connector fault at the crank sensor or coil pack. Clean/reseat or repair, then retest for spark.",
                                                "No visible damage": {
                                                    "diagnosis": "Sensor vs Module Check",
                                                    "tests": [{
                                                        "check": "Crank/Cam Sensor Signal Test",
                                                        "instruction": "Using a scan tool or scope, check for a crank/cam position sensor signal while cranking. Is a clean signal present?",
                                                        "options": {
                                                            "No signal": "Failed crankshaft or camshaft position sensor (whichever the scan tool flags). Replace the faulty sensor.",
                                                            "Signal present": "Sensor signal is present but spark still isn't happening. Ignition control module fault - replace the module."
                                                        }
                                                    }]
                                                }
                                            }
                                        },
                                        "Yes": {
                                            "diagnosis": "Fuel Delivery Check",
                                            "tests": [{
                                                "check": "Fuel Pump Prime",
                                                "instruction": "Turn the key to 'ON' (not crank) and listen near the tank for the fuel pump priming hum (2-3 seconds). Do you hear it?",
                                                "options": {
                                                    "No": {
                                                        "diagnosis": "Pump Circuit Check",
                                                        "tests": [{
                                                            "check": "Fuse and Relay Swap",
                                                            "instruction": "Check the fuel pump fuse, and swap the fuel pump relay with an identical relay from elsewhere in the fuse box. Does this fix it, or does one test bad?",
                                                            "options": {
                                                                "Yes, fuse or relay bad": "Blown fuel pump fuse or a failed relay. Replace whichever tested bad.",
                                                                "No, both test fine": {
                                                                    "diagnosis": "Pump Voltage Check",
                                                                    "tests": [{
                                                                        "check": "Voltage at Pump Connector",
                                                                        "instruction": "Have someone crank the engine while you check for voltage at the fuel pump's electrical connector. Is voltage present?",
                                                                        "options": {
                                                                            "Yes, voltage present": "Fuel pump has failed internally (it has power but won't run). Replace the fuel pump.",
                                                                            "No voltage": "Wiring fault between the relay and the fuel pump. Repair or replace the damaged wiring or connector."
                                                                        }
                                                                    }]
                                                                }
                                                            }
                                                        }]
                                                    },
                                                    "Yes": {
                                                        "diagnosis": "Pressure and Timing Check",
                                                        "tests": [{
                                                            "check": "Fuel Pressure Test",
                                                            "instruction": "Connect a fuel pressure gauge to the rail and check against spec while cranking. Is pressure within spec?",
                                                            "options": {
                                                                "No, out of spec": {
                                                                    "diagnosis": "Pressure Source Check",
                                                                    "tests": [{
                                                                        "check": "Regulator Vacuum Pinch Test",
                                                                        "instruction": "Pinch off the vacuum line to the fuel pressure regulator while watching the gauge. Does pressure rise?",
                                                                        "options": {
                                                                            "Yes, pressure rises": "Fuel pressure regulator is faulty. Replace the regulator.",
                                                                            "No change": "Regulator is fine, so fuel pump output is weak. Replace the fuel pump."
                                                                        }
                                                                    }]
                                                                },
                                                                "Yes, in spec": {
                                                                    "diagnosis": "Timing Check",
                                                                    "tests": [{
                                                                        "check": "Timing Marks Check",
                                                                        "instruction": "Rotate the engine by hand (or use a timing light if it will briefly run) and check that the timing marks align correctly. Are they aligned?",
                                                                        "options": {
                                                                            "No, misaligned": "Timing belt or chain has jumped or stretched. Replace the timing belt/chain and reset timing.",
                                                                            "Yes, aligned": "Fuel and timing both check out, so suspect a failed injector driver circuit or ECU fault preventing injector pulse. Test injector pulse with a noid light and check the ECU's injector driver circuit."
                                                                        }
                                                                    }]
                                                                }
                                                            }
                                                        }]
                                                    }
                                                }
                                            }]
                                        }
                                    }
                                }]
                            }
                        }
                    },
                    "Cranks slow/labored": {
                        "question": "Turn on the headlights with the engine off. Do they dim significantly or start out dim?",
                        "options": {
                            "Yes, dim/weak": {
                                "diagnosis": "Battery/Charging Check",
                                "tests": [{
                                    "check": "Battery Voltage",
                                    "instruction": "Check battery voltage at rest (engine off, ~30 min after last run). Is it below about 12.2V?",
                                    "options": {
                                        "Below 12.2V": "Weak or discharged battery. Charge fully and load-test; replace if it won't hold a charge.",
                                        "12.2V or higher": {
                                            "question": "Inspect the battery terminals and cable ends for corrosion or looseness. Found any?",
                                            "options": {
                                                "Yes": "Corroded/loose battery connection causing voltage drop under cranking load. Clean terminals and retorque connections.",
                                                "No": "Battery voltage is fine and connections are clean, so the starter motor itself is failing internally. Bench-test or replace the starter."
                                            }
                                        }
                                    }
                                }]
                            },
                            "No, lights stay bright": {
                                "diagnosis": "Mechanical Drag Check",
                                "tests": [{
                                    "check": "Free-Turn Check",
                                    "instruction": "With the spark plugs removed, try turning the engine over by hand (a socket on the crank pulley bolt works). Does it turn freely?",
                                    "options": {
                                        "No, binds/resists": "Internal engine mechanical binding (a seized component). This is a serious internal problem - have a shop inspect further before attempting to start again.",
                                        "Yes, turns freely": "The engine itself is fine, so the drag is in the starter motor binding internally. Replace the starter motor."
                                    }
                                }]
                            }
                        }
                    },
                    "Rapid clicking, doesn't crank": {
                        "diagnosis": "Cranking Circuit Check",
                        "tests": [{
                            "check": "Battery Voltage Under Load",
                            "instruction": "Check battery voltage at the terminals while attempting to start. Does it drop below about 9-10V?",
                            "options": {
                                "Yes, drops low": "Battery too weak/sulfated to supply cranking current. Load-test and replace if it fails; check the charging system afterward.",
                                "No, holds voltage": {
                                    "question": "If safely accessible, have someone lightly tap the starter housing with a wrench while you turn the key. Does it start?",
                                    "options": {
                                        "Yes": "Worn starter motor brushes or solenoid contacts. Replace the starter motor (the solenoid is usually integrated).",
                                        "No": {
                                            "diagnosis": "Relay vs Ground Check",
                                            "tests": [{
                                                "check": "Relay Swap Test",
                                                "instruction": "Swap the starter relay with an identical one from the fuse box. Does the engine now crank normally?",
                                                "options": {
                                                    "Yes": "Failed starter relay. Replace the relay.",
                                                    "No": "Relay wasn't the issue - a bad ground strap between the engine and chassis is the cause. Clean/replace the ground strap connection."
                                                }
                                            }]
                                        }
                                    }
                                }
                            }
                        }]
                    },
                    "Nothing at all (silent)": {
                        "diagnosis": "Dead Circuit Check",
                        "tests": [{
                            "check": "Battery Terminal Voltage",
                            "instruction": "With a multimeter directly on the battery posts (not the cables), do you read close to 12V?",
                            "options": {
                                "No, near 0V": "Battery itself is dead or has an internal fault. Charge and load-test; replace if it fails.",
                                "Yes, near 12V": {
                                    "diagnosis": "Cable/Fuse vs Switch Check",
                                    "tests": [{
                                        "check": "Cable and Fuse Check",
                                        "instruction": "Check the main fuse/fusible link near the battery, and inspect the battery cable ends for corrosion or looseness. Which do you find - a corroded/loose cable, a blown fuse, or neither?",
                                        "options": {
                                            "Corroded/loose cable": "Corroded or loose battery cable connection blocking power flow. Clean the terminals and retorque the connection.",
                                            "Blown fuse": "Blown main fuse or fusible link near the battery. Replace it (and check for a short if it blows again).",
                                            "Neither - both look fine": {
                                                "question": "If it's an automatic, try starting in Park and then in Neutral. Does it start in one but not the other?",
                                                "options": {
                                                    "Yes, one but not the other": {
                                                        "diagnosis": "Linkage vs Switch Check",
                                                        "tests": [{
                                                            "check": "Linkage Adjustment Check",
                                                            "instruction": "Visually check the shift linkage between the shifter and transmission for looseness or misadjustment. Is it loose or misadjusted?",
                                                            "options": {
                                                                "Yes, loose/misadjusted": "Misadjusted shift linkage preventing the neutral safety switch from engaging correctly. Adjust the linkage.",
                                                                "No, linkage is correct": "Linkage is fine, so it's a faulty neutral safety switch. Test and replace the switch."
                                                            }
                                                        }]
                                                    },
                                                    "Doesn't start in either": {
                                                        "diagnosis": "Relay vs Switch Check",
                                                        "tests": [{
                                                            "check": "Relay and Fuse Check",
                                                            "instruction": "Check the starter relay and its fuse (swap with an identical relay if possible). Does this fix it, or does one test bad?",
                                                            "options": {
                                                                "Yes, fixed it": "Blown starter fuse or failed starter relay. Replace whichever tested bad.",
                                                                "No change": "Relay and fuse are fine but there's no continuity to start - ignition switch failure. Replace the ignition switch."
                                                            }
                                                        }]
                                                    }
                                                }
                                            }
                                        }
                                    }]
                                }
                            }
                        }]
                    }
                }
            },
            "Performance Issue": {
                "question": "When does it happen?",
                "options": {
                    "Hesitation/Stumbling": {
                        "diagnosis": "Potential Fuel or Air Delivery Issue",
                        "tests": [{
                            "check": "Cold vs Warm Behavior",
                            "instruction": "Does the hesitation happen mostly when the engine is cold, or at all temperatures?",
                            "options": {
                                "Mostly when cold": {
                                    "diagnosis": "Coolant Sensor Check",
                                    "tests": [{
                                        "check": "Sensor Accuracy Check",
                                        "instruction": "Compare the coolant temperature sensor's reading (via a scan tool) to the engine's actual temperature. Does the sensor read noticeably colder than actual?",
                                        "options": {
                                            "Yes, reads colder": "Faulty coolant temperature sensor causing excess cold-start enrichment. Replace the sensor.",
                                            "No, reads accurately": "Sensor is accurate, so check for a vacuum leak that's worse when cold - inspect vacuum hoses and intake gaskets for cracks that seal better once warm."
                                        }
                                    }]
                                },
                                "All temperatures": {
                                    "diagnosis": "Air/Fuel Metering Check",
                                    "tests": [{
                                        "check": "Air Filter",
                                        "instruction": "Pull the air filter and inspect it. Is it visibly dirty or clogged?",
                                        "options": {
                                            "Dirty/clogged": "Restricted airflow from a dirty air filter. Replace the air filter.",
                                            "Filter looks fine": {
                                                "question": "Does the hesitation feel like a gradual power loss, or a sharp stumble/jerk?",
                                                "options": {
                                                    "Gradual power loss": {
                                                        "diagnosis": "Fuel Supply Check",
                                                        "tests": [{
                                                            "check": "Fuel Pressure Under Load",
                                                            "instruction": "With a fuel pressure gauge connected, accelerate hard and watch the gauge. Does pressure drop significantly under load?",
                                                            "options": {
                                                                "Yes, drops under load": "Fuel pump losing pressure under demand. Replace the fuel pump.",
                                                                "No, stays steady": "Pressure holds at the pump, so the restriction is downstream - a clogged fuel filter. Replace the fuel filter."
                                                            }
                                                        }]
                                                    },
                                                    "Sharp stumble/jerk": {
                                                        "diagnosis": "MAF vs Vacuum Leak Check",
                                                        "tests": [{
                                                            "check": "MAF Cleaning Test",
                                                            "instruction": "Clean the MAF sensor with proper MAF cleaner and clear any adaptations. Does the stumble go away?",
                                                            "options": {
                                                                "Yes, resolved": "Dirty MAF sensor was the cause. If it recurs, replace the MAF sensor.",
                                                                "No change": "MAF wasn't the issue - a vacuum leak is the cause. Inspect vacuum lines and intake gaskets for cracks (a smoke test pinpoints the exact leak location)."
                                                            }
                                                        }]
                                                    }
                                                }
                                            }
                                        }
                                    }]
                                }
                            }
                        }]
                    },
                    "Overheating": {
                        "diagnosis": "Cooling System Failure",
                        "tests": [{
                            "check": "Coolant Level",
                            "instruction": "Check reservoir and radiator (when cold). Is it full?",
                            "options": {
                                "No, low or empty": {
                                    "question": "Look under the car and around hoses/radiator/water pump for wet spots or dried coolant residue. Do you see a leak?",
                                    "options": {
                                        "Yes, visible leak": {
                                            "question": "Is the leak from a hose, the radiator itself, or near the water pump pulley (front of engine)?",
                                            "options": {
                                                "A hose": "Cracked or split coolant hose. Replace the hose and clamp, refill, and bleed the cooling system.",
                                                "The radiator": "Radiator core or seam leak. Repair or replace the radiator, then refill and bleed.",
                                                "Water pump area": "Water pump shaft seal failure. Replace the water pump."
                                            }
                                        },
                                        "No visible leak": {
                                            "diagnosis": "Internal Leak Check",
                                            "tests": [{
                                                "check": "Head Gasket Check",
                                                "instruction": "Check for white/sweet-smelling exhaust smoke and a milky film on the oil dipstick. Do you see either sign?",
                                                "options": {
                                                    "Yes": "Blown head gasket allowing coolant into the combustion chamber or oil. This needs professional repair - do not keep driving.",
                                                    "No": "No head gasket signs yet coolant is disappearing - have a shop pressure-test the cooling system to find a hidden leak point (heater core or a leak that only shows under pressure)."
                                                }
                                            }]
                                        }
                                    }
                                },
                                "Yes, full": {
                                    "diagnosis": "Cooling Circulation Check",
                                    "tests": [{
                                        "check": "Cooling Fan Operation",
                                        "instruction": "With the engine warmed up and temp rising, does the radiator cooling fan turn on?",
                                        "options": {
                                            "No": {
                                                "question": "Check the fan fuse and relay. Is either blown/faulty?",
                                                "options": {
                                                    "Yes, blown/faulty": "Blown fan fuse or a bad fan relay. Replace and confirm the fan now runs.",
                                                    "No, fuse/relay OK": {
                                                        "diagnosis": "Fan Motor vs Sensor Check",
                                                        "tests": [{
                                                            "check": "Direct Power Test",
                                                            "instruction": "Disconnect the fan and apply battery power directly to it. Does the fan spin?",
                                                            "options": {
                                                                "Yes, spins": "Fan motor is fine, so a coolant temperature sensor/switch isn't signaling it to turn on. Test and replace the faulty sensor/switch.",
                                                                "No, doesn't spin": "Fan motor itself has failed. Replace the fan motor."
                                                            }
                                                        }]
                                                    }
                                                }
                                            },
                                            "Yes": {
                                                "question": "Feel the upper radiator hose once the temp gauge is rising. Does it get hot along with the engine, or stay cool?",
                                                "options": {
                                                    "Stays cool": "Thermostat stuck closed, preventing coolant circulation. Replace the thermostat.",
                                                    "Gets hot normally": {
                                                        "diagnosis": "Pump vs Radiator Flow Check",
                                                        "tests": [{
                                                            "check": "Radiator Flow Check",
                                                            "instruction": "With the engine running and the radiator cap off (carefully, only when cool), check whether you see strong coolant circulation in the radiator neck. Is flow strong?",
                                                            "options": {
                                                                "Yes, strong flow": "Flow looks fine at the radiator, so the water pump impeller is slipping internally despite spinning (common with plastic impellers). Replace the water pump.",
                                                                "No, weak/no flow": "Radiator core is clogged internally, restricting flow. Flush or replace the radiator."
                                                            }
                                                        }]
                                                    }
                                                }
                                            }
                                        }
                                    }]
                                }
                            }
                        }]
                    },
                    "Rough idle or misfire feeling": {
                        "diagnosis": "Misfire / Rough Idle Check",
                        "tests": [{
                            "check": "Check Engine Light",
                            "instruction": "Does the check engine light come on, and if so, does it flash or stay steady?",
                            "options": {
                                "Yes, flashing": "Active misfire being detected by the ECU - a flashing light warns of catalytic converter damage risk. Stop driving hard soon; scan for the specific cylinder code (P030x) and check that cylinder's plug, coil, and injector (see the OBD-II Scanner tab).",
                                "Yes, steady": {
                                    "question": "How long since the spark plugs were last replaced?",
                                    "options": {
                                        "Over ~60,000 mi / 100,000 km, or unknown": {
                                            "diagnosis": "Plugs vs Coils Check",
                                            "tests": [{
                                                "check": "Post-Plug-Replacement Check",
                                                "instruction": "Replace the spark plugs first (cheaper and easier than coils). Does the rough idle/misfire go away?",
                                                "options": {
                                                    "Yes, resolved": "Worn spark plugs were the cause - resolved by replacing them.",
                                                    "No change": "Spark plugs weren't the issue - an ignition coil is failing. Test coil resistance on each cylinder and replace the faulty coil(s)."
                                                }
                                            }]
                                        },
                                        "Recently replaced": {
                                            "diagnosis": "Vacuum Leak vs Injector Check",
                                            "tests": [{
                                                "check": "Vacuum Leak Spray Test",
                                                "instruction": "With the engine idling, spray a small amount of carb/brake cleaner around intake gaskets and vacuum hose connections (in a well-ventilated area, away from anything hot). Does the idle change (rev up or smooth out) when you spray near a particular spot?",
                                                "options": {
                                                    "Yes, idle changes at a spot": "Vacuum leak found at that location. Repair or replace the leaking hose or gasket.",
                                                    "No change anywhere": "No vacuum leak found, so a fuel injector is dirty or failing. Have the injector professionally cleaned/flow-tested, and replace if it fails."
                                                }
                                            }]
                                        }
                                    }
                                },
                                "No light at all": {
                                    "diagnosis": "Throttle Body Check",
                                    "tests": [{
                                        "check": "Post-Cleaning Check",
                                        "instruction": "Clean the throttle body and idle air control (IAC) valve together, since they're related and cheap to service. Did the idle improve?",
                                        "options": {
                                            "Yes, improved": "Carbon buildup in the throttle body/IAC valve was causing the rough idle - resolved by cleaning.",
                                            "No change": "Cleaning didn't help, so check for a vacuum leak instead - inspect vacuum hoses and intake gaskets for cracks."
                                        }
                                    }]
                                }
                            }
                        }]
                    },
                    "Vibration at speed": {
                        "question": "Does the vibration change with vehicle speed, or stay the same regardless of speed?",
                        "options": {
                            "Changes/worse with speed": {
                                "question": "Do you feel it mainly through the steering wheel, the seat/floor, or both?",
                                "options": {
                                    "Steering wheel mainly": {
                                        "diagnosis": "Balance vs Rim Check",
                                        "tests": [{
                                            "check": "Wheel Balance Test",
                                            "instruction": "Have the front wheels balanced (quick and inexpensive). Does the vibration go away?",
                                            "options": {
                                                "Yes, resolved": "Wheel imbalance was the cause - resolved by balancing.",
                                                "No, still vibrates": "Balancing didn't fix it, meaning a bent rim is the cause even after 'correcting' for it. Inspect the rim for visible bending or have it checked on a lathe, and replace if bent."
                                            }
                                        }]
                                    },
                                    "Seat/floor mainly": {
                                        "diagnosis": "Driveline Check",
                                        "tests": [{
                                            "check": "CV/Driveshaft Inspection",
                                            "instruction": "Inspect CV joint boots for tears or grease leakage, and check the driveshaft for play at the U-joints. Which shows a problem?",
                                            "options": {
                                                "CV joint boot": "Torn CV joint boot has let the joint wear/fail. Replace the CV axle.",
                                                "U-joint/driveshaft play": "Worn universal joint causing driveline vibration. Replace the U-joint."
                                            }
                                        }]
                                    },
                                    "Both": {
                                        "diagnosis": "Tire Wear vs Alignment Check",
                                        "tests": [{
                                            "check": "Tire Wear Pattern Check",
                                            "instruction": "Inspect tread wear patterns on all four tires. Do you see uneven or cupped wear?",
                                            "options": {
                                                "Yes, uneven/cupped wear": "Uneven tire wear is causing the vibration. Replace the affected tire(s) - then get an alignment, since bad alignment is usually what caused the uneven wear in the first place.",
                                                "No, wear looks even": "Tread wear is even, so get a full wheel alignment to address the vibration directly."
                                            }
                                        }]
                                    }
                                }
                            },
                            "Stays the same regardless of speed": {
                                "diagnosis": "Mount Check",
                                "tests": [{
                                    "check": "Mount Inspection",
                                    "instruction": "With the engine off, visually inspect the engine and transmission mounts for cracking, separation, or excessive give. Which mount shows damage?",
                                    "options": {
                                        "Engine mount": "Worn or broken engine mount. Replace the engine mount.",
                                        "Transmission mount": "Worn or broken transmission mount. Replace the transmission mount."
                                    }
                                }]
                            }
                        }
                    }
                }
            }
        }
    },
    "Brakes & Steering": {
        "question": "Where do you feel the issue?",
        "options": {
            "Brake Pedal": {
                "question": "How does the pedal feel?",
                "options": {
                    "Spongy/Soft": {
                        "question": "Have you recently had brake work done, or added brake fluid?",
                        "options": {
                            "Yes, recent work/fluid": "Air was likely introduced into the lines during service. Bleed the brakes starting from the wheel farthest from the master cylinder.",
                            "No recent work": {
                                "diagnosis": "Brake Fluid System Check",
                                "tests": [{
                                    "check": "Brake Fluid Level",
                                    "instruction": "Check the brake fluid reservoir level. Is it low?",
                                    "options": {
                                        "Low": {
                                            "question": "Inspect each wheel for fluid staining or wetness at the caliper/wheel cylinder. Any leak visible?",
                                            "options": {
                                                "Yes": {
                                                    "question": "At the wheel with the wet spot, is the fluid coming from the caliper itself, a wheel cylinder (drum brakes), or a visible line/hose?",
                                                    "options": {
                                                        "Caliper": "Leaking brake caliper (piston seal failure). Rebuild or replace the caliper.",
                                                        "Wheel cylinder": "Leaking wheel cylinder (drum brakes). Replace the wheel cylinder.",
                                                        "Line or hose": "Leaking brake line or hose. Replace the damaged line/hose."
                                                    }
                                                },
                                                "No visible leak": "Fluid loss without an external leak suggests the master cylinder is bypassing internally. Pressure-test and replace the master cylinder if it's bypassing."
                                            }
                                        },
                                        "Normal": {
                                            "diagnosis": "Air vs Hose Check",
                                            "tests": [{
                                                "check": "Post-Bleed Check",
                                                "instruction": "Bleed all four brakes thoroughly. Does the pedal firm up afterward?",
                                                "options": {
                                                    "Yes, firms up": "Trapped air was the cause - resolved by bleeding.",
                                                    "No, still soft": "Pedal is still soft after a proper bleed, so a rubber brake hose is ballooning under pressure. Inspect and replace the swelling hose."
                                                }
                                            }]
                                        }
                                    }
                                }]
                            }
                        }
                    },
                    "Pulsating/Shaking": {
                        "question": "Does the pulsation happen every time you brake, or mainly from higher speeds?",
                        "options": {
                            "Every time, even low speed": "Warped front rotors. Have them measured and resurfaced or replaced.",
                            "Mainly from higher speed": {
                                "question": "Do you also feel a wobble in the steering wheel, not just the pedal?",
                                "options": {
                                    "Yes, steering wheel too": {
                                        "diagnosis": "Rotor vs Bearing Check",
                                        "tests": [{
                                            "check": "Wheel Bearing Play Check",
                                            "instruction": "With the wheel off the ground, grab the tire at 12 and 6 o'clock and check for play/looseness in the wheel bearing. Is there noticeable play?",
                                            "options": {
                                                "Yes, noticeable play": "Worn front wheel bearing. Replace the wheel bearing.",
                                                "No play": "Bearing is fine, so it's rotor warp alone. Resurface or replace the front rotors."
                                            }
                                        }]
                                    },
                                    "Only in the pedal": {
                                        "question": "Are the rear brakes disc (rotors) or drum?",
                                        "options": {
                                            "Disc": "Rear rotor warp. Resurface or replace the rear rotors.",
                                            "Drum": "Out-of-round rear brake drum. Resurface or replace the drum."
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "Goes to the floor": {
                        "question": "Does the pedal slowly sink to the floor when held at a stop, or did it drop suddenly while driving?",
                        "options": {
                            "Sinks slowly while held": "Internal master cylinder bypass from worn seals. Replace the master cylinder. Do not drive until repaired.",
                            "Dropped suddenly": {
                                "question": "Check under the car and at each wheel for fresh brake fluid. Found a leak?",
                                "options": {
                                    "Yes": {
                                        "question": "Is the leak from a brake line/hose, or from a caliper/wheel cylinder at one wheel?",
                                        "options": {
                                            "Line/hose": "Ruptured brake line or hose. Vehicle is unsafe to drive - replace the damaged line/hose and fully bleed before driving again.",
                                            "Caliper/wheel cylinder": "Blown caliper or wheel cylinder seal at that wheel. Vehicle is unsafe to drive - replace the caliper or wheel cylinder and fully bleed before driving again."
                                        }
                                    },
                                    "No visible leak": "Internal seal failure in the master cylinder or a failed proportioning valve - this needs a shop's brake pressure gauge to isolate safely. Have the brake system inspected immediately; do not drive."
                                }
                            }
                        }
                    }
                }
            },
            "Steering Wheel": {
                "question": "Is steering difficult, or does it pull to one side?",
                "options": {
                    "Heavy/Hard to turn": {
                        "question": "Is this hydraulic power steering (belt-driven pump) or electric power steering?",
                        "options": {
                            "Hydraulic / not sure": {
                                "diagnosis": "Power Steering Fluid Check",
                                "tests": [{
                                    "check": "Power Steering Fluid Level",
                                    "instruction": "Check the power steering fluid reservoir. Is the level low?",
                                    "options": {
                                        "Low": {
                                            "question": "Where do you see fluid stains - near the steering rack, the pump, or a hose?",
                                            "options": {
                                                "Steering rack": "Leaking steering rack seal. Replace or rebuild the steering rack.",
                                                "Pump": "Leaking power steering pump seal. Replace the pump or its seal.",
                                                "Hose": "Leaking power steering hose. Replace the damaged hose."
                                            }
                                        },
                                        "Normal": "Fluid is low without an obvious leak, suggesting a slow seep at the pump shaft seal. Top off and monitor."
                                    }
                                }]
                            },
                            "Electric power steering": "Likely an EPS motor or steering control module fault. Scan for steering-system-specific fault codes."
                        }
                    },
                    "Pulling to one side": {
                        "diagnosis": "Tire and Alignment Check",
                        "tests": [{
                            "check": "Tire Pressure",
                            "instruction": "Check tire pressure on all four tires. Are they equal and at the recommended PSI?",
                            "options": {
                                "No, uneven pressure": "Uneven tire pressure causing the pull. Inflate all tires to spec and retest before investigating further.",
                                "Yes, pressures are even": {
                                    "question": "Has the vehicle hit a significant pothole or curb recently?",
                                    "options": {
                                        "Yes": {
                                            "diagnosis": "Suspension vs Alignment Check",
                                            "tests": [{
                                                "check": "Suspension Visual Check",
                                                "instruction": "Visually inspect tie rods, control arms, and the strut/spring near the impact side for bending or damage. Do you see visible damage?",
                                                "options": {
                                                    "Yes, damage visible": "Bent suspension component from the impact. Replace the damaged part (tie rod, control arm, etc.).",
                                                    "No visible damage": "No damage found, so it's an alignment change from the impact. Get a wheel alignment."
                                                }
                                            }]
                                        },
                                        "No": {
                                            "diagnosis": "Alignment vs Caliper Check",
                                            "tests": [{
                                                "check": "Caliper Drag Check",
                                                "instruction": "After a short drive, carefully feel the temperature of each front wheel/rotor - they should be similarly warm. Is one noticeably hotter?",
                                                "options": {
                                                    "Yes, one hotter": "Dragging brake caliper on that side, pulling the car toward it. Inspect and free up or replace the caliper.",
                                                    "No, similar temps": "No dragging caliper, so it's gradual alignment drift. Get a wheel alignment."
                                                }
                                            }]
                                        }
                                    }
                                }
                            }
                        }]
                    }
                }
            }
        }
    },
    "Electrical & Lights": {
        "question": "What electrical component is failing?",
        "options": {
            "Exterior Lights": {
                "question": "Is it one bulb out, or multiple lights / an entire side not working?",
                "options": {
                    "Just one bulb": "A single burned-out bulb. Replace the bulb; check the corresponding fuse if a new bulb still doesn't light.",
                    "Multiple lights out on one side": "Bad ground connection or a failed relay serving that circuit. Check the grounding point and relevant relay.",
                    "All exterior lights out": {
                        "question": "Check the main lighting fuse in the fuse box. Is it blown?",
                        "options": {
                            "Yes, blown": "Blown main lighting fuse, possibly from a short. Replace the fuse; if it blows again, look for chafed wiring.",
                            "No, fuse is fine": {
                                "diagnosis": "Switch vs BCM Check",
                                "tests": [{
                                    "check": "Switch Continuity Test",
                                    "instruction": "Test the headlight switch for continuity in the 'on' position with a multimeter. Does it show continuity?",
                                    "options": {
                                        "Yes, continuity is fine": "Switch is fine, so it's a Body Control Module (BCM) fault. Have the BCM's lighting outputs tested.",
                                        "No continuity": "Failed headlight switch. Replace the switch."
                                    }
                                }]
                            }
                        }
                    }
                }
            },
            "Interior Electronics": {
                "question": "Which accessories are affected - just one, or several at once?",
                "options": {
                    "Just one accessory": {
                        "diagnosis": "Dedicated Circuit Check",
                        "tests": [{
                            "check": "Dedicated Fuse Check",
                            "instruction": "Check that accessory's dedicated fuse. Is it blown?",
                            "options": {
                                "Yes, blown": "Blown fuse for that accessory. Replace the fuse (and investigate why if it blows again).",
                                "No, fuse is fine": "Fuse is fine, so the accessory itself (or its switch/motor) has failed. Replace or repair that specific component."
                            }
                        }]
                    },
                    "Several accessories at once": {
                        "question": "Check the main accessory/interior fuse(s). Any blown?",
                        "options": {
                            "Yes": "Blown shared accessory fuse, likely from a short in one of the connected circuits. Replace the fuse, then isolate which device is drawing excess current.",
                            "No": {
                                "diagnosis": "Ground vs BCM Check",
                                "tests": [{
                                    "check": "Ground Strap Check",
                                    "instruction": "Inspect and clean the chassis ground strap connections. After cleaning, do the accessories work normally again?",
                                    "options": {
                                        "Yes, resolved": "Corroded or loose chassis ground strap was the cause - resolved by cleaning.",
                                        "No change": "Grounds are fine, so it's a Body Control Module (BCM) fault. Have the BCM tested/diagnosed."
                                    }
                                }]
                            }
                        }
                    }
                }
            },
            "Battery keeps dying": {
                "question": "Does it die overnight/while parked, or while you're driving/idling?",
                "options": {
                    "Dies while parked": {
                        "diagnosis": "Parasitic Draw Check",
                        "tests": [{
                            "check": "Parasitic Draw",
                            "instruction": "With the car off and locked, measure current draw in series with the negative terminal. Is it above roughly 50mA?",
                            "options": {
                                "Yes, high draw": "Parasitic electrical draw from a circuit that isn't powering down. Pull fuses one at a time to isolate the offending circuit.",
                                "No, draw is normal": "Normal draw means the battery itself is likely old/weak. Load-test and replace if it fails."
                            }
                        }]
                    },
                    "Dies while driving": {
                        "diagnosis": "Charging System Check",
                        "tests": [{
                            "check": "Alternator Output Voltage",
                            "instruction": "Check alternator output voltage with the engine running (should read ~13.5-14.5V). Is it in range?",
                            "options": {
                                "No, out of range": {
                                    "diagnosis": "Belt vs Alternator Check",
                                    "tests": [{
                                        "check": "Belt Check",
                                        "instruction": "Check the serpentine belt for proper tension and glazing/wear. Is the belt slipping or worn?",
                                        "options": {
                                            "Yes, slipping/worn": "Slipping or worn serpentine belt not turning the alternator fast enough. Replace/re-tension the belt.",
                                            "No, belt is fine": "Belt is fine, so the alternator itself has failed. Replace the alternator."
                                        }
                                    }]
                                },
                                "Yes, in range": "Charging system checks out - recheck for a parasitic draw or a weak battery instead."
                            }
                        }]
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
         max-width:860px; margin:24px auto; padding:0 16px; }
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
  .text-input { padding:9px; border:1px solid #ced4da; border-radius:4px; font-size:14px; min-width:180px; }
  .testbox { border:1px solid #dee2e6; border-radius:4px; padding:12px; margin:10px 0; background:#ffffff; }
  .pidnote { font-size:0.85em; color:#495057; margin-top:6px; }
  .search-link { display:inline-block; background:#4285f4; color:#ffffff !important; padding:9px 14px;
                 border-radius:4px; text-decoration:none; margin:8px 8px 8px 0; }
  .table-wrap { max-height:340px; overflow:auto; border:1px solid #dee2e6; border-radius:4px; margin-top:8px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th, td { padding:6px 8px; text-align:left; border-bottom:1px solid #eee; }
  th { background:#f1f3f5; position:sticky; top:0; }
  .breadcrumb { font-size:0.85em; color:#6c757d; margin-bottom:6px; }
</style>
</head>
<body>
<h2>Professional Diagnostic Assistant
  <a href="#" id="start-over-link" style="font-size:0.5em; margin-left:12px; color:#0d6efd;">Start Over</a>
</h2>
<div id="screen"></div>

<script>
const DATA = __DATA_JSON__;
const OBDB_RAW_BASE = "https://raw.githubusercontent.com/OBDb/{repo}/main/signalsets/v3/default.json";

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

function mkBox(html, cls) {
  const d = document.createElement('div');
  d.className = 'box ' + cls;
  d.innerHTML = html;
  return d;
}

function mkInput(placeholder, value) {
  const i = document.createElement('input');
  i.type = 'text';
  i.placeholder = placeholder;
  i.className = 'text-input';
  if (value) i.value = value;
  return i;
}

// ---------- OBDb live fetch (runs in the browser) ----------

async function tryFetchRepo(repo) {
  const res = await fetch(OBDB_RAW_BASE.replace('{repo}', repo));
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return await res.json();
}

function parseSignalset(json) {
  const signals = {};
  (json.commands || []).forEach(cmd => {
    (cmd.signals || []).forEach(sig => {
      signals[sig.id] = {
        name: sig.name || sig.id,
        unit: (sig.fmt || {}).unit || '',
        header: cmd.hdr || '?',
        pid: cmd.cmd || {}
      };
    });
  });
  return signals;
}

async function fetchObdbSignalset(make, model) {
  make = make.trim(); model = model.trim();
  const candidates = [];
  if (model) {
    candidates.push(`${make}-${model}`.replace(/\s+/g, '-'));
    candidates.push(`${make}-${model.replace(/([A-Za-z])(\d)/g, '$1-$2')}`.replace(/\s+/g, '-'));
  }
  candidates.push(make.replace(/\s+/g, '-'));

  let sawNetworkError = false;
  for (const repo of [...new Set(candidates)]) {
    try {
      const json = await tryFetchRepo(repo);
      if (json) return { signals: parseSignalset(json), repo };
    } catch (e) {
      sawNetworkError = true;
    }
  }
  if (sawNetworkError) throw new Error('network');
  return { signals: null, repo: null };
}

// ---------- PID matching for test steps ----------

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

// ---------- vehicle selection ----------

function showVehiclePrompt() {
  const el = clearScreen();
  el.appendChild(mkBox("<b>Enter your vehicle</b> to enable the Live PID Reference (optional - everything else works without it).", 'neutral'));

  const row = document.createElement('div');
  row.className = 'btnrow';
  const v = DATA.vehicle || {};
  const makeInput = mkInput('Make (e.g. Toyota)', v.make);
  const modelInput = mkInput('Model (e.g. Camry)', v.model);
  const yearInput = mkInput('Year (e.g. 2015)', v.year);
  row.append(makeInput, modelInput, yearInput);
  el.appendChild(row);

  const btnRow = document.createElement('div');
  btnRow.className = 'btnrow';

  const loadBtn = document.createElement('button');
  loadBtn.className = 'btn btn-success';
  loadBtn.textContent = 'Load Vehicle';
  loadBtn.addEventListener('click', () => loadVehicle(makeInput.value, modelInput.value, yearInput.value));
  btnRow.appendChild(loadBtn);

  const skipBtn = document.createElement('button');
  skipBtn.className = 'btn';
  skipBtn.textContent = 'Skip for now';
  skipBtn.addEventListener('click', () => {
    DATA.vehicle = DATA.vehicle || { make: '', model: '', year: '' };
    showInitialPrompt();
  });
  btnRow.appendChild(skipBtn);
  el.appendChild(btnRow);
}

async function loadVehicle(make, model, year) {
  DATA.vehicle = { make: (make || '').trim(), model: (model || '').trim(), year: (year || '').trim() };
  const el = clearScreen();
  el.appendChild(mkBox(`Looking up OBDb data for ${escapeHtml(DATA.vehicle.year)} ${escapeHtml(DATA.vehicle.make)} ${escapeHtml(DATA.vehicle.model)}...`, 'neutral'));

  try {
    const { signals, repo } = await fetchObdbSignalset(DATA.vehicle.make, DATA.vehicle.model);
    DATA.pid_signals = signals || {};
    DATA.pid_repo = repo;
    if (signals) {
      showInitialPrompt(`Loaded ${Object.keys(signals).length} live PID signals from OBDb repo <b>${escapeHtml(repo)}</b>.`, 'success');
    } else {
      showInitialPrompt(`No OBDb repository found for '<b>${escapeHtml(DATA.vehicle.make)} ${escapeHtml(DATA.vehicle.model)}</b>' - continuing without live PID data.`, 'warning');
    }
  } catch (e) {
    DATA.pid_signals = {};
    DATA.pid_repo = null;
    showInitialPrompt(`Couldn't reach GitHub to fetch live PID data. If you opened this file directly (file://), browsers block that - try hosting it (e.g. GitHub Pages) instead. Continuing without live PID data.`, 'warning');
  }
}

// ---------- main screen ----------

function showInitialPrompt(noteHtml, noteCls) {
  const el = clearScreen();
  const v = DATA.vehicle || {};
  const heading = document.createElement('h3');
  heading.textContent = (v.make || v.model) ? `Diagnostic for ${v.year || ''} ${v.make || ''} ${v.model || ''}`.trim() : 'Diagnostic Assistant';
  el.appendChild(heading);

  if (noteHtml) el.appendChild(mkBox(noteHtml, noteCls || 'neutral'));

  const prompt = document.createElement('div');
  prompt.innerHTML = "<b>Do you have a code, want to describe the issue, or look up this vehicle's live sensor PIDs?</b>";
  el.appendChild(prompt);

  const row = document.createElement('div');
  row.className = 'btnrow';

  const codeInput = mkInput('Enter OBD-II Code');
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

  const vehicleBtn = document.createElement('button');
  vehicleBtn.className = 'btn';
  vehicleBtn.textContent = 'Change Vehicle';
  vehicleBtn.addEventListener('click', showVehiclePrompt);
  row.appendChild(vehicleBtn);

  el.appendChild(row);
}

function showPidReference() {
  const el = clearScreen();
  const v = DATA.vehicle || {};
  el.appendChild(Object.assign(document.createElement('h3'), { textContent: `Diagnostic for ${v.year || ''} ${v.make || ''} ${v.model || ''}`.trim() || 'Diagnostic Assistant' }));

  const signals = DATA.pid_signals || {};
  const ids = Object.keys(signals);

  if (ids.length === 0) {
    el.appendChild(mkBox(
      `No live PID data loaded yet. Use "Change Vehicle" to enter a make/model (this needs the page to be hosted over http/https - it won't work if opened as a local file).`,
      'warning'
    ));
  } else {
    el.appendChild(mkBox(
      `Loaded <b>${ids.length}</b> signals from OBDb repo <a href="https://github.com/OBDb/${escapeHtml(DATA.pid_repo)}" target="_blank">${escapeHtml(DATA.pid_repo)}</a>. These are live PIDs for a real scan tool/ELM327 adapter - matching test steps in the decision tree show the exact PID to query.`,
      'success'
    ));
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
  back.addEventListener('click', () => showInitialPrompt());
  el.appendChild(back);
}

// ---------- DTC lookup ----------

function appendSearchHelper(el, resultText) {
  const v = DATA.vehicle || {};
  const query = encodeURIComponent(`${v.year || ''} ${v.make || ''} ${v.model || ''} ${resultText}`);
  const link = document.createElement('a');
  link.href = `https://www.google.com/search?q=${query}`;
  link.target = '_blank';
  link.className = 'search-link';
  link.textContent = 'Repair Guide Search \u{1F50D}';
  el.appendChild(link);

  const restart = document.createElement('button');
  restart.className = 'btn btn-success';
  restart.textContent = 'Start New Triage';
  restart.addEventListener('click', () => showInitialPrompt());
  el.appendChild(restart);
}

function lookupCode(rawCode) {
  const code = (rawCode || '').toUpperCase().trim();
  const res = DATA.obd_database[code];
  const el = clearScreen();
  if (res) {
    el.appendChild(mkBox(`<b>${escapeHtml(code)}:</b> ${escapeHtml(res.desc)}`, 'success'));
    appendSearchHelper(el, `${code} ${res.desc}`);
  } else {
    el.appendChild(mkBox('Code not found. Describe the symptoms instead below.', 'danger'));
    renderSymptomPromptInto(el);
  }
}

// ---------- free-text symptom description: TF-IDF + cosine-similarity classifier ----------
//
// Each category below is backed by a small set of example phrases (its
// "training documents"). On analysis, the same TF-IDF vectorization is
// applied to the user's text and every category, then ranked by cosine
// similarity - genuine vector-space text classification, not a
// does-the-string-contain-this-substring check. See README for a fuller
// explanation.

const SYMPTOM_CATEGORIES = [
  { label: "Won't Start (engine cranks)", path: ["Engine", "Starting Issues", "Cranks normally, just won't start"],
    examples: ["the engine cranks but won't start", "it turns over but never starts", "starter spins fine but the engine won't fire", "cranks strong yet doesn't start", "engine turns over normally but refuses to start", "won't start even though it cranks"] },
  { label: "Slow/Labored Cranking", path: ["Engine", "Starting Issues", "Cranks slow/labored"],
    examples: ["engine cranks slowly", "slow labored cranking when starting", "struggles to turn over when starting", "sluggish weak cranking sound", "starter sounds weak and slow", "takes a long time to crank over"] },
  { label: "Rapid Clicking, No Crank", path: ["Engine", "Starting Issues", "Rapid clicking, doesn't crank"],
    examples: ["rapid clicking noise when turning the key", "just clicks repeatedly and won't crank", "hear fast clicking under the hood when starting", "key turns but only clicking happens", "rapid click click click no crank at all"] },
  { label: "Completely Dead / No Response", path: ["Engine", "Starting Issues", "Nothing at all (silent)"],
    examples: ["completely dead nothing happens when i turn the key", "totally silent no response at all", "no lights no sound nothing when starting", "dashboard completely dark and unresponsive", "car is entirely dead"] },
  { label: "Hesitation or Stumbling", path: ["Engine", "Performance Issue", "Hesitation/Stumbling"],
    examples: ["car hesitates and stumbles when accelerating", "engine bogs down under acceleration", "sputters and loses power when i press the gas", "lacks power and stumbles going uphill", "jerky hesitation when speeding up", "car stalls momentarily then continues"] },
  { label: "Overheating", path: ["Engine", "Performance Issue", "Overheating"],
    examples: ["engine is overheating", "temperature gauge climbs into the red", "steam coming from under the hood", "coolant is boiling over", "running really hot on the highway", "temp light comes on after driving a while"] },
  { label: "Rough Idle / Misfire", path: ["Engine", "Performance Issue", "Rough idle or misfire feeling"],
    examples: ["rough idle at stop lights", "engine shakes and misfires at idle", "jerking sensation while idling", "check engine light flashing with rough running", "sputtering idle feels uneven", "misfire feeling under light acceleration"] },
  { label: "Vibration at Speed", path: ["Engine", "Performance Issue", "Vibration at speed"],
    examples: ["vibration that gets worse at highway speed", "steering wheel shakes at speed", "shimmy and wobble over 50 mph", "car vibrates a lot on the freeway", "shaking through the seat at higher speeds"] },
  { label: "Spongy or Soft Brake Pedal", path: ["Brakes & Steering", "Brake Pedal", "Spongy/Soft"],
    examples: ["brake pedal feels spongy and soft", "mushy brake pedal that sinks slightly", "pedal feels squishy when braking", "soft brakes need more pressure than usual", "air feels like its in the brake lines"] },
  { label: "Brake Pedal Pulsates/Shakes", path: ["Brakes & Steering", "Brake Pedal", "Pulsating/Shaking"],
    examples: ["brake pedal pulsates when stopping", "steering shakes when i brake at speed", "pedal pulses and shudders during braking", "warped rotors causing brake vibration", "shaking sensation only when braking hard"] },
  { label: "Brake Pedal Goes to the Floor", path: ["Brakes & Steering", "Brake Pedal", "Goes to the floor"],
    examples: ["brake pedal goes all the way to the floor", "pedal sinks to the floor when i hold it", "lost my brakes and pedal hit the floor", "brakes failed and pedal went down completely", "no resistance pedal drops to the floorboard"] },
  { label: "Steering Heavy / Hard to Turn", path: ["Brakes & Steering", "Steering Wheel", "Heavy/Hard to turn"],
    examples: ["steering is very heavy and hard to turn", "power steering feels stiff", "hard to turn the wheel especially at low speed", "steering wheel requires a lot of effort", "no power assist steering feels heavy"] },
  { label: "Steering Pulls to One Side", path: ["Brakes & Steering", "Steering Wheel", "Pulling to one side"],
    examples: ["car pulls to the left while driving", "vehicle drifts to one side on its own", "steering pulls right constantly", "car veers to a side when i let go of the wheel", "alignment feels off pulling one direction"] },
  { label: "Exterior Light Problem", path: ["Electrical & Lights", "Exterior Lights"],
    examples: ["headlight is out", "tail light not working", "brake light bulb burned out", "turn signal doesn't light up", "one of my exterior lights stopped working"] },
  { label: "Interior Electronics Problem", path: ["Electrical & Lights", "Interior Electronics"],
    examples: ["radio won't turn on", "power windows stopped working", "dashboard lights are out", "infotainment screen is dead", "interior electronics not responding"] },
  { label: "Battery Keeps Dying", path: ["Electrical & Lights", "Battery keeps dying"],
    examples: ["battery dies overnight", "car battery keeps dying every morning", "dead battery every time i park it", "parasitic draw killing my battery", "battery drains even when the car is off"] },
];

const STOPWORDS = new Set(["the", "a", "an", "is", "are", "it", "to", "of", "and", "in", "on", "at",
  "this", "that", "my", "car", "i", "im", "its", "it's", "when", "does", "do", "with", "for", "has",
  "have", "from", "just", "really", "very", "seems", "seem", "feels", "feel", "get", "gets", "getting"]);

function tokenize(text) {
  return (text || "").toLowerCase().split(/[^a-z0-9']+/).filter(w => w && !STOPWORDS.has(w));
}

function termFreq(doc) {
  const counts = {};
  doc.forEach(w => { counts[w] = (counts[w] || 0) + 1; });
  const total = doc.length || 1;
  const tf = {};
  Object.keys(counts).forEach(w => { tf[w] = counts[w] / total; });
  return tf;
}

let _idf = null, _categoryVectors = null;

function buildClassifier() {
  const docs = SYMPTOM_CATEGORIES.map(c => tokenize(c.examples.join(" ")));
  const df = {};
  docs.forEach(doc => { new Set(doc).forEach(w => { df[w] = (df[w] || 0) + 1; }); });
  const n = docs.length;
  _idf = {};
  Object.keys(df).forEach(w => { _idf[w] = Math.log((n + 1) / (df[w] + 1)) + 1; }); // smoothed idf
  _categoryVectors = docs.map(doc => tfidfVector(doc));
}

function tfidfVector(doc) {
  const tf = termFreq(doc);
  const vec = {};
  Object.keys(tf).forEach(w => { vec[w] = tf[w] * (_idf[w] || 0); });
  return vec;
}

function cosineSimilarity(vecA, vecB) {
  let dot = 0, normA = 0, normB = 0;
  const keys = new Set([...Object.keys(vecA), ...Object.keys(vecB)]);
  keys.forEach(k => {
    const a = vecA[k] || 0, b = vecB[k] || 0;
    dot += a * b; normA += a * a; normB += b * b;
  });
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

function classifySymptoms(rawText) {
  if (!_categoryVectors) buildClassifier();
  const queryVec = tfidfVector(tokenize(rawText));
  return SYMPTOM_CATEGORIES
    .map((c, i) => ({ category: c, score: cosineSimilarity(queryVec, _categoryVectors[i]) }))
    .sort((a, b) => b.score - a.score);
}

function walkTree(path) {
  let node = DATA.diagnostic_tree;
  for (const key of path) {
    node = (node && node.options) ? node.options[key] : node[key];
  }
  return node;
}

function renderSymptomPromptInto(el) {
  const label = document.createElement('div');
  label.innerHTML = '<b>Describe the issue, in a full sentence if you can:</b>';
  el.appendChild(label);

  const input = mkInput('e.g., the engine hesitates and stumbles when I accelerate');
  input.style.width = '70%';
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

const MIN_CONFIDENT_SCORE = 0.03; // below this, treat as "no real lexical match"
const TOP_N_MATCHES = 3;

function analyzeSymptoms(rawText) {
  const ranked = classifySymptoms(rawText);
  const top = ranked.slice(0, TOP_N_MATCHES).filter(r => r.score > MIN_CONFIDENT_SCORE);

  if (top.length === 0) {
    renderNode(DATA.diagnostic_tree); // no confident match - fall back to manual category browse
    return;
  }
  renderSymptomMatches(rawText, top);
}

function renderSymptomMatches(rawText, top) {
  const el = clearScreen();
  el.appendChild(mkBox(`Based on "<i>${escapeHtml(rawText)}</i>", here's what this looks most like (ranked by text similarity to known symptom patterns):`, 'neutral'));

  const totalScore = top.reduce((sum, r) => sum + r.score, 0);
  top.forEach(r => {
    const pct = Math.round((r.score / totalScore) * 100);
    const row = document.createElement('div');
    row.className = 'testbox';
    row.innerHTML = `<b>${escapeHtml(r.category.label)}</b> - ${pct}% confidence
      <div style="background:#e9ecef; border-radius:3px; height:8px; margin-top:6px;">
        <div style="background:#0d6efd; width:${pct}%; height:100%; border-radius:3px;"></div>
      </div>`;
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary';
    btn.textContent = 'This one';
    btn.style.marginTop = '8px';
    btn.addEventListener('click', () => renderNode(walkTree(r.category.path)));
    row.appendChild(btn);
    el.appendChild(row);
  });

  const manualBtn = document.createElement('button');
  manualBtn.className = 'btn';
  manualBtn.textContent = 'None of these - browse manually';
  manualBtn.addEventListener('click', () => renderNode(DATA.diagnostic_tree));
  el.appendChild(manualBtn);
}

// ---------- unified tree dispatcher (question / tests / conclusion) ----------

function renderNode(node) {
  if (typeof node === 'string') { renderConclusion(node); return; }
  if (node.tests) { renderTests(node); return; }
  renderQuestion(node);
}

function renderQuestion(node) {
  const el = clearScreen();
  el.appendChild(mkBox(`<b>${escapeHtml(node.question || 'Select an option:')}</b>`, 'neutral'));

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
  el.appendChild(mkBox(escapeHtml(text), 'success'));
  appendSearchHelper(el, text);
}

// ---------- boot ----------

function boot() {
  document.getElementById('start-over-link').addEventListener('click', e => {
    e.preventDefault();
    showInitialPrompt();
  });
  if (DATA.vehicle && DATA.vehicle.make) {
    showInitialPrompt();
  } else {
    showVehiclePrompt();
  }
}
boot();
</script>
</body>
</html>
"""


def build_app(make, model, year, filename="diagnostic_assistant.html"):
    """make/model/year can be left blank - the generated app will then open
    straight to its own vehicle-selection screen instead of a pre-baked one."""
    signals, repo = None, None
    if make.strip():
        print(f"Looking up OBDb data for {year} {make} {model} ...")
        try:
            signals, repo = fetch_obdb_signalset(make, model)
        except OBDbNetworkError as e:
            print(f"Couldn't reach GitHub ({e}). Skipping pre-baked PID data.")
        if signals:
            print(f"Found {len(signals)} signals in OBDb repo '{repo}'.")
        elif make.strip():
            print("No OBDb repo found for this vehicle.")

    data = {
        "vehicle": {"make": make, "model": model, "year": year} if make.strip() else None,
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
    print("Leave these blank to have the app open straight to its own vehicle-selection screen.")
    make = input("Vehicle make (optional, e.g. Toyota): ").strip()
    model = input("Vehicle model (optional, e.g. Camry): ").strip()
    year = input("Vehicle year (optional, e.g. 2015): ").strip()

    fname = build_app(make, model, year)

    try:
        from google.colab import files
        files.download(fname)
        print("Download started - open the file once it lands in your Downloads folder.")
    except ImportError:
        print(f"Not running in Colab - open {fname} directly in your browser.")
