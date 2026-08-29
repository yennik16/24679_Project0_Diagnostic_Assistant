"""
Local OBD-II diagnostic trouble code (DTC) database.

This is a static reference table of common trouble codes and is
independent of the OBDb live-PID data pulled in build_diagnostic_app.py -
DTCs (P0300, P0420, ...) are fault-history codes; OBDb signals are live
sensor readings. See the README for the distinction.

Each code maps to the desc key with the accompanying text about the likely cause.
index.htmls lookupCode() function expects one of these codes
These codes are what a standard OBD2 automotive scanner would spit out when reading
a check engine light or similar for the underlying fault code causing it
"""

OBD_CODES = {
    #library of generic codes. Not vehicle specific like the PID codes from the github I found but should
    #suffice for my purposes.
    #P01xx are fuel and air related, P03xx are ignition related, P04xx are emission related, P05xx are misc,
    #and P07xx are transmission related. These serve to make up the quickest diagnostic functionality,
    #rather than the more in depth and intelligent decision tree based diagnostics
    "P0100": {"desc": "Mass or Volume Air Flow Circuit Malfunction. Likely causes: dirty/failing MAF sensor, torn intake ducting, or a wiring fault at the MAF connector."},
    "P0101": {"desc": "MAF Circuit Range/Performance Problem. Likely causes: dirty MAF element, a vacuum leak downstream of the MAF, or aftermarket intake miscalibration."},
    "P0113": {"desc": "Intake Air Temperature Sensor 1 Circuit High. Likely causes: open circuit, corroded connector, or a failed IAT sensor."},
    "P0128": {"desc": "Coolant Thermostat (temp below regulating threshold). Likely causes: thermostat stuck open, low coolant, or a faulty coolant temp sensor."},
    "P0130": {"desc": "O2 Sensor Circuit Malfunction (Bank 1, Sensor 1). Likely causes: failed upstream O2 sensor, wiring damage, or an exhaust leak near the sensor."},
    "P0171": {"desc": "System Too Lean (Bank 1). Likely causes: vacuum leak, dirty MAF sensor, weak fuel pump/clogged injectors, or an exhaust leak before the O2 sensor."},
    "P0174": {"desc": "System Too Lean (Bank 2). Likely causes: vacuum leak on bank 2, fuel delivery restriction, or a failing MAF sensor."},
    "P0175": {"desc": "System Too Rich (Bank 2). Likely causes: leaking fuel injector, failed fuel pressure regulator, or a faulty O2 sensor."},
    "P0300": {"desc": "Random or Multiple Cylinder Misfire Detected. Likely causes: worn spark plugs, failing ignition coil(s), a vacuum leak, or low fuel pressure."},
    "P0301": {"desc": "Cylinder 1 Misfire Detected. Likely causes: bad spark plug/coil on cylinder 1, a fuel injector fault, or low compression."},
    "P0302": {"desc": "Cylinder 2 Misfire Detected. Likely causes: bad spark plug/coil on cylinder 2, a fuel injector fault, or low compression."},
    "P0303": {"desc": "Cylinder 3 Misfire Detected. Likely causes: bad spark plug/coil on cylinder 3, a fuel injector fault, or low compression."},
    "P0304": {"desc": "Cylinder 4 Misfire Detected. Likely causes: bad spark plug/coil on cylinder 4, a fuel injector fault, or low compression."},
    "P0325": {"desc": "Knock Sensor 1 Circuit Malfunction. Likely causes: failed knock sensor, damaged wiring, or a loose sensor mount."},
    "P0335": {"desc": "Crankshaft Position Sensor Circuit Malfunction. Likely causes: failed crank sensor, a damaged reluctor ring, or a wiring fault."},
    "P0340": {"desc": "Camshaft Position Sensor Circuit Malfunction. Likely causes: failed cam sensor, timing chain/belt wear, or a wiring fault."},
    "P0401": {"desc": "EGR Flow Insufficient. Likely causes: clogged EGR valve/passages, a failed EGR valve, or carbon buildup."},
    "P0420": {"desc": "Catalytic Converter Efficiency Below Threshold (Bank 1). Likely causes: deteriorated catalytic converter, a failing O2 sensor, or an exhaust leak."},
    "P0430": {"desc": "Catalytic Converter Efficiency Below Threshold (Bank 2). Likely causes: deteriorated catalytic converter, a failing O2 sensor, or an exhaust leak."},
    "P0442": {"desc": "Evaporative Emission System Leak Detected (small leak). Likely causes: loose/damaged gas cap, a cracked EVAP hose, or a faulty purge valve."},
    "P0455": {"desc": "Evaporative Emission System Leak Detected (large leak). Likely causes: gas cap left off/loose, a disconnected EVAP hose, or a failed purge/vent valve."},
    "P0500": {"desc": "Vehicle Speed Sensor Malfunction. Likely causes: failed VSS, damaged wiring, or an ABS tone ring issue."},
    "P0505": {"desc": "Idle Control System Malfunction. Likely causes: faulty IAC valve, a dirty throttle body, or a vacuum leak."},
    "P0506": {"desc": "Idle RPM Lower Than Expected. Likely causes: carbon buildup in the throttle body, a vacuum leak, or a failing IAC valve."},
    "P0507": {"desc": "Idle RPM Higher Than Expected. Likely causes: vacuum leak, a stuck-open IAC valve, or throttle body carbon buildup."},
    "P0562": {"desc": "System Voltage Low. Likely causes: weak/failing battery, a failing alternator, or corroded battery terminals."},
    "P0563": {"desc": "System Voltage High. Likely causes: overcharging alternator/regulator, a bad battery cell, or a wiring fault."},
    "P0700": {"desc": "Transmission Control System Malfunction (informational - check the TCM for a specific code)."},
    "P0715": {"desc": "Input/Turbine Speed Sensor Circuit Malfunction. Likely causes: failed input speed sensor, a wiring fault, or low transmission fluid."},
    "P0720": {"desc": "Output Speed Sensor Circuit Malfunction. Likely causes: failed output speed sensor, a damaged tone ring, or a wiring fault."},
    "P0730": {"desc": "Incorrect Gear Ratio. Likely causes: low/degraded transmission fluid, worn clutch packs, or a valve body fault."},
    "P0740": {"desc": "Torque Converter Clutch Circuit Malfunction. Likely causes: failed TCC solenoid, low transmission fluid, or a wiring fault."},
}

# Kept for compatibility with the original notebook script's import signature.
KNOWN_MODELS = []
