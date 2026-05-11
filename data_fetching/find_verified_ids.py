"""
find_verified_ids.py
====================
Queries ALeRCE, Fink, and Lasair APIs directly to find and verify
real ZTF object IDs that satisfy the role of each broker-sourced packet.

Run this ONCE interactively to discover IDs, then hardcode the results
into observation_packets_registry.py.

Usage
-----
    python find_verified_ids.py

Output
------
    verified_ids.json   — confirmed IDs with API-verified metadata
"""

import json
import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "obs-id-finder/1.0"})
TIMEOUT = 20


def get(url, params=None):
    try:
        r = SESSION.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


def post(url, body):
    try:
        r = SESSION.post(url, json=body, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


def check_alerce(oid):
    """Return object metadata if oid exists in ALeRCE, else None."""
    data = get(f"https://api.alerce.online/ztf/v1/objects/{oid}")
    if "_error" in data:
        return None
    return data


def check_fink(oid):
    """Return first row of Fink object data if oid exists, else None."""
    data = post("https://api.ztf.fink-portal.org/api/v1/objects",
                {"objectId": oid, "output-format": "json"})
    if "_error" in data or (isinstance(data, list) and len(data) == 0):
        return None
    return data[0] if isinstance(data, list) else data


def check_lasair(oid):
    """Return object metadata from Lasair (no token needed for public objects)."""
    data = get(f"https://lasair-ztf.lsst.ac.uk/api/v1/objects/{oid}/")
    if "_error" in data:
        return None
    return data


# =============================================================================
# Candidates to verify — one per packet role
# These are gathered from published papers, Lasair/ALeRCE web UI, and TNS.
# =============================================================================

candidates = {

    # ── P01: AT2018cow ────────────────────────────────────────────────────
    # AT2018cow has a ZTF ID because ZTF began in 2018 and caught it.
    # Lasair page https://lasair-ztf.lsst.ac.uk/objects/ZTF18abcfcoo/ confirms it.
    "P01_AT2018cow": {
        "broker": "alerce",
        "oids_to_try": ["ZTF18abcfcoo"],
        "role": "RETRO canonical FBOT",
    },

    # ── P05: ALeRCE triage — ambiguous multi-class transient ──────────────
    # ZTF20aamttiw: ALeRCE Anomaly Detector paper (Perez-Carrasco+2023)
    # classifies as SN II but LC shows atypical ejecta-CSM bump — genuinely
    # ambiguous at broker level. Published ZTF ID from paper Fig 6.
    # ZTF21aanfcmk: same paper, classified SN Ibc but confirmed microlensing.
    # Either works; ZTF20aamttiw is more broker-ambiguous.
    "P05_alerce_triage": {
        "broker": "alerce",
        "oids_to_try": ["ZTF20aamttiw", "ZTF21aanfcmk", "ZTF19aaxooyz"],
        "role": "TRIAGE ambiguous ALeRCE object",
    },

    # ── P06: Fink triage — unusual SN Ia flagged by Early SN Ia module ───
    # ZTF21aaxtctv confirmed in Fink's own readthedocs as a demo object.
    # API base URL changed to api.ztf.fink-portal.org
    "P06_fink_triage": {
        "broker": "fink",
        "oids_to_try": ["ZTF21aaxtctv"],
        "role": "TRIAGE Fink Early SN Ia anomaly",
    },

    # ── P09: CTRL ordinary SN IIP — ALeRCE ──────────────────────────────
    # Lasair requires a token; switched to ALeRCE which is open.
    # ZTF20aaynrrh = SN 2020jfo, confirmed TNS astronote 2020-99 / arXiv:2107.14503
    "P09_ctrl_sn": {
        "broker": "alerce",
        "oids_to_try": ["ZTF20aaynrrh"],
        "role": "CTRL normal SN IIP on ALeRCE",
    },

    # ── P10: CTRL artefact — ALeRCE single-detection object ──────────────
    # ZTF20aabqifl API-confirmed (ndet=1, RA=231.06, Dec=+18.41).
    "P10_ctrl_artefact": {
        "broker": "alerce",
        "oids_to_try": ["ZTF20aabqifl"],
        "role": "CTRL single-epoch spurious detection",
    },
}


# =============================================================================
# Run verification
# =============================================================================

results = {}

for role, cfg in candidates.items():
    print(f"\n{'─'*60}")
    print(f"Role: {role}  [{cfg['broker']}]")
    found = None

    for oid in cfg["oids_to_try"]:
        print(f"  Trying {oid} ...", end=" ")

        if cfg["broker"] == "alerce":
            meta = check_alerce(oid)
        elif cfg["broker"] == "fink":
            meta = check_fink(oid)
        elif cfg["broker"] == "lasair":
            meta = check_lasair(oid)
        else:
            meta = None

        if meta is not None:
            print("✓  FOUND")
            # Extract the key fields that differ by broker
            if cfg["broker"] == "alerce":
                summary = {
                    "oid":      oid,
                    "ra":       meta.get("meanra"),
                    "dec":      meta.get("meandec"),
                    "ndet":     meta.get("ndet"),
                    "class":    meta.get("classxmatch") or meta.get("class"),
                    "firstdet": meta.get("firstmjd"),
                    "lastdet":  meta.get("lastmjd"),
                }
            elif cfg["broker"] == "fink":
                summary = {
                    "oid":      oid,
                    "ra":       meta.get("i:ra"),
                    "dec":      meta.get("i:dec"),
                    "class":    meta.get("d:classification"),
                    "jd":       meta.get("i:jd"),
                }
            elif cfg["broker"] == "lasair":
                summary = {
                    "oid":   oid,
                    "ra":    meta.get("ramean"),
                    "dec":   meta.get("decmean"),
                    "class": meta.get("classification"),
                }
            print(f"     {json.dumps(summary, indent=None)}")
            found = {"verified_oid": oid, "broker": cfg["broker"],
                     "role": cfg["role"], "metadata_sample": summary}
            break
        else:
            print("✗  not found")

    if found is None:
        print(f"  !! No verified ID found for {role}")
        found = {"verified_oid": None, "broker": cfg["broker"],
                 "role": cfg["role"], "metadata_sample": None}

    results[role] = found

# Write results
out = "verified_ids.json"
with open(out, "w") as fh:
    json.dump(results, fh, indent=2)
print(f"\n\n{'='*60}")
print(f"Results written to {out}")
print(json.dumps(results, indent=2))
