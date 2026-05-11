"""
fetch_observation_packets.py
============================
Single external acquisition agent.  For every ObservationPacket in the
registry it:

  1. Calls the relevant broker / archive API to fetch metadata (JSON)
  2. Downloads every binary data product (FITS, PNG, CSV) to disk
  3. Writes an enriched packet.json where every data-product field is a
     LOCAL RELATIVE PATH, not a URL

The downstream LangGraph multi-agent system reads these files only.
It never touches the network.

Output layout
-------------
packets/
    manifest.json
    packet_01_AT2018cow/
        packet.json
        data/
            cutout_r.fits
            lightcurve.csv
            stamp_science.fits
            stamp_template.fits
            stamp_difference.fits
            alert_meta.json
            probabilities.json
            simbad.json
            catalog_row.json
            catalog_row.csv
    packet_02_FRB20121102A/
        ...

Dependencies
------------
    pip install requests astropy astroquery pandas

Usage
-----
    python fetch_observation_packets.py --all [--out-dir ./packets]
    python fetch_observation_packets.py --packet 1
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import requests
import pandas as pd

from observation_packets_registry import OBSERVATION_PACKETS


# =============================================================================
# HTTP session
# =============================================================================

TIMEOUT = 30
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "obs-packet-agent/1.0"})


def _get(url: str, params: dict | None = None,
         accept: str = "application/json") -> requests.Response | None:
    try:
        r = SESSION.get(url, params=params, timeout=TIMEOUT,
                        headers={"Accept": accept})
        r.raise_for_status()
        return r
    except Exception as exc:
        print(f"      [WARN] GET failed ({url}): {exc}")
        return None


def _post(url: str, body: dict,
          accept: str = "application/json") -> requests.Response | None:
    try:
        r = SESSION.post(url, json=body, timeout=TIMEOUT,
                         headers={"Accept": accept})
        r.raise_for_status()
        return r
    except Exception as exc:
        print(f"      [WARN] POST failed ({url}): {exc}")
        return None


# ── disk writers ──────────────────────────────────────────────────────────────

def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _rel(path: Path, anchor: Path) -> str:
    """Return path relative to anchor as a POSIX string."""
    return path.relative_to(anchor).as_posix()


# =============================================================================
# Per-source downloaders
# Each returns a flat dict:  {label: "data/filename.ext"}
# All paths are relative to the per-packet directory (pkt_dir).
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Sky image cutout — PS1 for Dec > -30, SkyView/DSS2 for southern fields
#
# PS1 covers Dec > -30°.  Everything further south (GOODS-S, EDF-S, etc.)
# falls back to the NASA SkyView FITS cutout service using DSS2 Red,
# which covers the full sky at ~1 arcsec/pix.
# ─────────────────────────────────────────────────────────────────────────────

PS1_DEC_LIMIT = -30.0   # degrees; PS1 footprint hard southern boundary


def _download_ps1(ra: float, dec: float, data_dir: Path, filt: str = "r") -> dict:
    """Pan-STARRS FITS cutout.  Only call when dec > PS1_DEC_LIMIT."""
    out: dict = {}

    # PS1 CGI scripts require the query string built manually — requests params=
    # encoding breaks the CGI parser (it rejects URL-encoded + in dec sign).
    # Step 1 — resolve mosaic filename for this sky position
    filename_url = (
        f"https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
        f"?ra={ra}&dec={dec}&filters={filt}"
    )
    try:
        r = SESSION.get(filename_url, timeout=TIMEOUT,
                        headers={"Accept": "text/plain"})
        r.raise_for_status()
    except Exception as exc:
        print(f"      [WARN] PS1 filenames failed: {exc}")
        return out

    # Response: header row then one data row per skycell overlap
    # Header columns: projcell subcell ra dec filter mjd type filename shortname badflag
    lines = [ln for ln in r.text.strip().splitlines() if ln.strip()]
    data_lines = [ln for ln in lines if not ln.startswith("projcell") and not ln.startswith("#")]
    if not data_lines:
        print(f"      [WARN] PS1: no {filt}-band coverage at ({ra:.4f}, {dec:+.4f})")
        return out

    # filename is the 8th column (0-indexed: 7), shortname is 9th
    cols = data_lines[0].split()
    fits_candidates = [tok for tok in cols if tok.endswith(".fits")]
    if not fits_candidates:
        print(f"      [WARN] PS1: no .fits token in data row: {data_lines[0]!r}")
        return out
    fits_filename = fits_candidates[0]

    # Step 2 — download the FITS cutout
    fits_url = (
        f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"
        f"?ra={ra}&dec={dec}&size=300&format=fits&red={fits_filename}"
    )
    try:
        r2 = SESSION.get(fits_url, timeout=TIMEOUT, headers={"Accept": "*/*"})
        r2.raise_for_status()
    except Exception as exc:
        print(f"      [WARN] PS1 fitscut failed: {exc}")
        return out

    if len(r2.content) < 200:
        print("      [WARN] PS1 FITS content empty or too small")
        return out

    p = data_dir / f"cutout_{filt}.fits"
    _write(p, r2.content)
    out[f"cutout_{filt}_fits"] = _rel(p, data_dir.parent)
    print(f"      [OK] PS1 {filt}-band FITS  →  {p.name}  ({len(r2.content)//1024} kB)")
    return out


def _download_skyview(ra: float, dec: float, data_dir: Path,
                      survey: str = "DSS2 Red") -> dict:
    """
    NASA SkyView FITS cutout — full-sky coverage.
    Returns a 300×300 pixel FITS at ~1 arcsec/pix.
    """
    out: dict = {}
    url = "https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl"
    params = {
        "Survey":   survey,
        "Position": f"{ra},{dec}",
        "Size":     "0.083",      # degrees ≈ 5 arcmin
        "Pixels":   "300",
        "Return":   "FITS",
        "Coordinates": "J2000",
    }
    r = _get(url, params=params, accept="*/*")
    if r is None or len(r.content) < 200:
        print(f"      [WARN] SkyView: empty response for ({ra:.4f}, {dec:+.4f})")
        return out

    # SkyView returns either raw FITS bytes or an HTML redirect with a fits link
    if r.content[:6] == b"SIMPLE":
        # Raw FITS in the response body
        fits_bytes = r.content
    else:
        # Parse the HTML to find the .fits link
        import re
        match = re.search(rb'href="([^"]+\.fits)"', r.content)
        if not match:
            print("      [WARN] SkyView: could not parse FITS link from HTML response")
            return out
        fits_link = match.group(1).decode()
        if not fits_link.startswith("http"):
            fits_link = "https://skyview.gsfc.nasa.gov" + fits_link
        r2 = _get(fits_link, accept="*/*")
        if r2 is None or len(r2.content) < 200:
            return out
        fits_bytes = r2.content

    survey_slug = survey.replace(" ", "_").lower()
    p = data_dir / f"cutout_{survey_slug}.fits"
    _write(p, fits_bytes)
    out[f"cutout_{survey_slug}_fits"] = _rel(p, data_dir.parent)
    print(f"      [OK] SkyView {survey}  →  {p.name}  ({len(fits_bytes)//1024} kB)")
    return out


def download_sky_cutout(ra: float, dec: float, pkt_dir: Path) -> dict:
    """
    Entry point for image cutout download.
    Routes to PS1 (north) or SkyView/DSS2 (south) based on declination.
    """
    data_dir = pkt_dir / "data"
    if dec >= PS1_DEC_LIMIT:
        print(f"      → PS1 cutout  (Dec={dec:+.2f}° is within PS1 footprint)")
        return _download_ps1(ra, dec, data_dir)
    else:
        print(f"      → SkyView/DSS2 cutout  (Dec={dec:+.2f}° is south of PS1 limit)")
        return _download_skyview(ra, dec, data_dir)


# ─────────────────────────────────────────────────────────────────────────────
# ALeRCE
# ─────────────────────────────────────────────────────────────────────────────

def download_alerce(oid: str, pkt_dir: Path) -> dict:
    base     = f"https://api.alerce.online/ztf/v1/objects/{oid}"
    data_dir = pkt_dir / "data"
    out: dict = {}

    # alert metadata
    r = _get(base)
    if r:
        p = data_dir / "alert_meta.json"
        _write_json(p, r.json())
        out["alert_meta"] = _rel(p, pkt_dir)
        print(f"      [OK] alert_meta.json")

    # broker class probabilities
    r = _get(f"{base}/probabilities")
    if r:
        p = data_dir / "probabilities.json"
        _write_json(p, r.json())
        out["probabilities"] = _rel(p, pkt_dir)
        print(f"      [OK] probabilities.json")

    # light curve → CSV
    r = _get(f"{base}/lightcurve")
    if r:
        lc  = r.json()
        det = lc.get("detections", [])
        nd  = lc.get("non_detections", [])
        if det:
            p = data_dir / "lightcurve.csv"
            _write_csv(p, det)
            out["lightcurve_csv"] = _rel(p, pkt_dir)
            print(f"      [OK] lightcurve.csv  ({len(det)} epochs)")
        if nd:
            p2 = data_dir / "non_detections.csv"
            _write_csv(p2, nd)
            out["non_detections_csv"] = _rel(p2, pkt_dir)

    # stamps: fetch via IRSA ZTF cutout service using the most recent candid
    # ALeRCE /stamps endpoint is deprecated; use alert_meta candid + IRSA
    meta = out.get("alert_meta")   # already written as JSON path — re-read
    try:
        import json as _json
        meta_path = pkt_dir / out.get("alert_meta", "data/alert_meta.json")
        meta_data = _json.loads(meta_path.read_text()) if meta_path.exists() else {}
        candid = meta_data.get("lastcandid") or meta_data.get("firstcandid")
        if candid:
            for kind, col in [("science", "red"), ("template", "blue"), ("difference", "green")]:
                # IRSA ZTF cutout service — public, no auth
                stamp_url = (
                    f"https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/"
                    f"{str(candid)[:4]}/{str(candid)[4:8]}/{str(candid)[8:14]}/"
                    f"ztf_{str(candid)[:4]}{str(candid)[4:8]}{str(candid)[8:14]}_"
                    f"{str(oid)[-5:]}_c01_o_q1_sciimg.fits"
                )
                # Simpler: use ZTF alert archive cutout
                r2 = _get(
                    "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/",
                    accept="*/*"
                )
            # Fallback: record candid for manual retrieval
            p = data_dir / "stamps_candid.txt"
            p.write_text(str(candid))
            out["stamps_candid"] = _rel(p, pkt_dir)
            print(f"      [OK] stamps_candid.txt  (candid={candid}; use IRSA ZTF to retrieve stamps)")
    except Exception as exc:
        print(f"      [WARN] stamps: {exc}")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fink Portal
# ─────────────────────────────────────────────────────────────────────────────

def download_fink(oid: str, pkt_dir: Path) -> dict:
    base     = "https://api.ztf.fink-portal.org/api/v1"
    data_dir = pkt_dir / "data"
    out: dict = {}

    # light curve rows (Fink epoch table IS the light curve)
    r = _post(f"{base}/objects", {"objectId": oid, "output-format": "json"})
    if r:
        rows = r.json()
        if isinstance(rows, list) and rows:
            p = data_dir / "lightcurve.csv"
            _write_csv(p, rows)
            out["lightcurve_csv"] = _rel(p, pkt_dir)
            print(f"      [OK] lightcurve.csv  ({len(rows)} rows)")

    # classification scores
    r = _post(f"{base}/objects",
              {"objectId": oid,
               "columns": "d:classification,d:rf_snia_vs_nonia,d:nalerthist,d:cdsxmatch",
               "output-format": "json"})
    if r:
        p = data_dir / "classification.json"
        _write_json(p, r.json())
        out["classification"] = _rel(p, pkt_dir)
        print(f"      [OK] classification.json")

    # stamp cutouts — Fink requires a specific candid in the POST body
    # Extract most recent candid from the light curve rows already fetched
    try:
        import json as _json
        rows_raw = _post(f"{base}/objects",
                         {"objectId": oid, "output-format": "json",
                          "columns": "i:candid,i:jd"})
        if isinstance(rows_raw, list) and rows_raw:
            candid = rows_raw[0].get("i:candid")
            if candid:
                for kind in ("Science", "Template", "Difference"):
                    r = _post(f"{base}/cutouts",
                              {"objectId": oid, "candid": candid,
                               "kind": kind, "output-format": "fits"})
                    if r and len(r.content) > 200:
                        sp = data_dir / f"stamp_{kind.lower()}.fits"
                        _write(sp, r.content)
                        out[f"stamp_{kind.lower()}_fits"] = _rel(sp, pkt_dir)
                        print(f"      [OK] stamp_{kind.lower()}.fits  ({len(r.content)//1024} kB)")
                    else:
                        print(f"      [WARN] Fink {kind} stamp empty or failed")
    except Exception as exc:
        print(f"      [WARN] Fink stamps: {exc}")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# CHIME catalog CSV
# ─────────────────────────────────────────────────────────────────────────────

_CHIME_CACHE = Path("cache/chime_catalog1.json")

def _ensure_chime_catalog() -> pd.DataFrame | None:
    """
    Load the CHIME/FRB Catalog 1. 
    Uses the new JSON-based catalog from Google Cloud Storage.
    """
    if _CHIME_CACHE.exists():
        try:
            return pd.read_json(_CHIME_CACHE)
        except Exception:
            pass

    # Primary: try the new JSON catalog URL
    url = "https://storage.googleapis.com/chimefrb-dev.appspot.com/catalog1/chimefrbcat1.json"
    
    try:
        print(f"      [INFO] Attempting CHIME download from {url}...")
        r = SESSION.get(url, timeout=TIMEOUT)
        
        if r.status_code == 200:
            _CHIME_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _CHIME_CACHE.write_bytes(r.content)
            print("      [OK] CHIME catalog1 downloaded successfully")
            return pd.read_json(_CHIME_CACHE)
        else:
            print(f"      [WARN] CHIME API returned {r.status_code}")
    except Exception as exc:
        print(f"      [WARN] CHIME main API failed: {exc}")

    # Fallback: Canadian Astronomy Data Centre (CADC) static archive (CSV)
    cadc_url = "https://www.canfar.net/storage/list/CHIME_FRB/pub/catalog1/catalog.csv"
    try:
        r = SESSION.get(cadc_url, timeout=TIMEOUT)
        if r.status_code == 200:
            csv_cache = _CHIME_CACHE.with_suffix(".csv")
            csv_cache.write_bytes(r.content)
            print("      [OK] CHIME catalog1 loaded from CADC mirror (CSV)")
            return pd.read_csv(csv_cache, low_memory=False)
    except Exception as exc:
        print(f"      [WARN] CADC fallback failed: {exc}")

    print("      [ERROR] All CHIME sources failed. Please run: pip install cfod")
    return None

def _normalise_frb_name(value: Any) -> str:
    """Return a compact FRB identifier for tolerant catalogue matching."""
    s = str(value).strip().lower()
    for token in ("frb", " ", "-", "_"):
        s = s.replace(token, "")
    return s


def _find_chime_rows(df: pd.DataFrame, tns_name: str) -> pd.DataFrame:
    """
    Locate CHIME catalogue rows for an FRB without assuming a fixed schema.

    CHIME catalogue exports have changed column names across access paths
    (cfod vs CSV API), so this searches likely name columns first, then all
    object/string columns as a last resort.
    """
    target = _normalise_frb_name(tns_name)
    if not target:
        return df.iloc[0:0]

    preferred_columns = [
        "tns_name",
        "tns_name_frb",
        "source_name",
        "event_name",
        "repeater_name",
        "frb_name",
        "name",
    ]

    # First try exact normalised equality in likely identifier columns.
    for col in preferred_columns:
        if col in df.columns:
            s = df[col].map(_normalise_frb_name)
            rows = df[s == target]
            if not rows.empty:
                return rows

    # Then try likely identifier columns by substring containment.
    # This catches names like "FRB20121102A/121102".
    for col in preferred_columns:
        if col in df.columns:
            s = df[col].map(_normalise_frb_name)
            rows = df[s.str.contains(target, na=False) | s.map(lambda x: x in target)]
            if not rows.empty:
                return rows

    # Finally scan all textual columns. This is slower but robust for small CSVs.
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            s = df[col].map(_normalise_frb_name)
            rows = df[s == target]
            if not rows.empty:
                return rows

    return df.iloc[0:0]


def download_chime(tns_name: str, pkt_dir: Path) -> dict:
    data_dir = pkt_dir / "data"
    out: dict = {}

    df = _ensure_chime_catalog()
    if df is None:
        return out

    print(f"      [INFO] CHIME catalog columns: {', '.join(map(str, df.columns))}")
    rows = _find_chime_rows(df, tns_name)
    if rows.empty:
        print(f"      [WARN] CHIME: no catalogue row matched '{tns_name}'")
        out["chime_catalog_available"] = True
        out["chime_match"] = False
        return out

    row_list = rows.to_dict(orient="records")

    p = data_dir / "catalog_row.json"
    _write_json(p, row_list)
    out["catalog_row_json"] = _rel(p, pkt_dir)

    p2 = data_dir / "catalog_row.csv"
    _write_csv(p2, row_list)
    out["catalog_row_csv"] = _rel(p2, pkt_dir)

    ef = row_list[0].get("excluded_flag", "0")
    excluded = str(ef).strip() == "1"
    out["excluded_flag"] = excluded
    out["chime_catalog_available"] = True
    out["chime_match"] = True
    print(f"      [OK] CHIME catalog row  (excluded={excluded})  →  {p.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIMBAD TAP
# ─────────────────────────────────────────────────────────────────────────────

def download_simbad(simbad_id: str, pkt_dir: Path) -> dict:
    data_dir = pkt_dir / "data"
    out: dict = {}

    # SIMBAD TAP: escape single quotes, and avoid coordinate-format names
    # (e.g. "CEERS J141946.36+525632.8") which break ADQL parsing.
    # Use the object resolver endpoint instead for robustness.
    safe_id = simbad_id.replace("'", "\'")
    adql = (
        f"SELECT main_id, ra, dec, otype_txt, z_value "
        f"FROM basic JOIN ident ON basic.oid=ident.oidref "
        f"WHERE id='{safe_id}'"
    )
    try:
        # Build URL manually — SIMBAD TAP is sensitive to param encoding
        import urllib.parse
        query_url = (
            "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"
            "?REQUEST=doQuery&LANG=ADQL&FORMAT=json"
            f"&QUERY={urllib.parse.quote(adql)}"
        )
        r = SESSION.get(query_url, timeout=TIMEOUT)
        r.raise_for_status()
        result = r.json()
        if result.get("data"):
            p = data_dir / "simbad.json"
            _write_json(p, result)
            out["simbad_json"] = _rel(p, pkt_dir)
            print(f"      [OK] simbad.json")
        else:
            # Fallback: SIMBAD script service — handles common names better
            script = f"query id {simbad_id}\nformat object \"main_id ra dec otype z_value\""
            r2 = SESSION.post("https://simbad.u-strasbg.fr/simbad/sim-script",
                              data={"script": f"output console=off script=off\nformat object fmt1 \"%-30MAIN_ID %RA %DEC %OTYPE %Z_VALUE\n\"\nquery id {simbad_id}"},
                              timeout=TIMEOUT)
            if r2.ok and "No astronomical object found" not in r2.text:
                p = data_dir / "simbad.txt"
                _write(p, r2.content)
                out["simbad_txt"] = _rel(p, pkt_dir)
                print(f"      [OK] simbad.txt (script fallback)")
            else:
                print(f"      [WARN] SIMBAD: object not found for '{simbad_id}'")
    except Exception as exc:
        print(f"      [WARN] SIMBAD query failed: {exc}")
    return out


# =============================================================================
# Master dispatch
# =============================================================================

def populate_packet(pkt: dict, out_dir: Path, index: int) -> dict:
    oids = pkt["object_or_event_id"]
    mods = pkt["modality"]

    slug = (
        oids.get("TNS_name") or oids.get("Euclid_id") or
        oids.get("survey_id") or oids.get("artefact_name", "unknown")
    ).replace(" ", "_").replace("/", "_")[:30]

    pkt_dir  = out_dir / f"packet_{index:02d}_{slug}"
    data_dir = pkt_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    fetched: dict = {}

    # ── ALeRCE (P05, P10) ─────────────────────────────────────────────────
    if "ZTF_oid" in oids and "ALeRCE_url" in oids:
        oid = oids["ZTF_oid"]
        print(f"    → ALeRCE  [{oid}]")
        fetched.update(download_alerce(oid, pkt_dir))
        ra, dec = oids.get("RA_deg"), oids.get("Dec_deg")
        if ra and dec and "image_cutout" in mods:
            fetched.update(download_sky_cutout(ra, dec, pkt_dir))

    # ── Fink (P06) ─────────────────────────────────────────────────────────
    elif "Fink_url" in oids and "ZTF_oid" in oids:
        oid = oids["ZTF_oid"]
        print(f"    → Fink  [{oid}]")
        fetched.update(download_fink(oid, pkt_dir))
        ra, dec = oids.get("RA_deg"), oids.get("Dec_deg")
        if ra and dec and "image_cutout" in mods:
            fetched.update(download_sky_cutout(ra, dec, pkt_dir))

    # ── CHIME (P02, P12) ──────────────────────────────────────────────────
    elif "CHIME_catalog1_tns_name" in oids or "CHIME_catalog1_tns" in oids:
        tns = oids.get("CHIME_catalog1_tns_name") or oids.get("CHIME_catalog1_tns")
        print(f"    → CHIME  [{tns}]")
        fetched.update(download_chime(tns, pkt_dir))

    # ── Archive-anchored (P01, P03, P04, P07, P08, P11) ───────────────────
    else:
        simbad_id = (oids.get("SIMBAD_id") or oids.get("IAU_coord_name")
                     or oids.get("TNS_name") or oids.get("common_name"))
        if simbad_id and "catalogue_entry" in mods:
            print(f"    → SIMBAD  [{simbad_id}]")
            fetched.update(download_simbad(simbad_id, pkt_dir))

        ra, dec = oids.get("RA_deg"), oids.get("Dec_deg")
        if ra and dec and "image_cutout" in mods:
            print(f"    → PS1 cutout  [({ra:.4f}, {dec:+.4f})]")
            fetched.update(download_sky_cutout(ra, dec, pkt_dir))

    # ── Write enriched packet.json ────────────────────────────────────────
    enriched = dict(pkt)
    enriched["populated_data_products"] = fetched
    enriched["fetch_log"] = {
        "packet_dir":  str(pkt_dir),
        "files":       [v for v in fetched.values() if isinstance(v, str)],
        "errors":      [],
    }

    _write_json(pkt_dir / "packet.json", enriched)
    n_files = len(enriched["fetch_log"]["files"])
    print(f"    ✓ packet.json  ({n_files} file(s) on disk)")
    return enriched


# =============================================================================
# Entry point
# =============================================================================

def run(indices: list[int], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for i in indices:
        pkt = OBSERVATION_PACKETS[i - 1]
        print(f"\n{'─'*60}")
        print(f"Packet {i:02d}/{len(OBSERVATION_PACKETS)}  [{pkt['experiment_type']}]  {pkt['mission']}")
        enriched = populate_packet(pkt, out_dir, i)
        log      = enriched["fetch_log"]
        manifest.append({
            "index":      i,
            "packet_dir": log["packet_dir"],
            "mission":    pkt["mission"],
            "experiment": pkt["experiment_type"],
            "modalities": pkt["modality"],
            "labels":     pkt["initial_pipeline_labels"],
            "files":      log["files"],
        })
        time.sleep(0.5)

    _write_json(out_dir / "manifest.json", manifest)
    print(f"\n{'='*60}")
    print(f"✓  manifest.json  →  {out_dir / 'manifest.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--packet", type=int, metavar="N")
    g.add_argument("--all", action="store_true")
    parser.add_argument("--out-dir", default="./packets")
    args = parser.parse_args()

    indices = (list(range(1, len(OBSERVATION_PACKETS) + 1))
               if args.all else [args.packet])
    run(indices, Path(args.out_dir))


if __name__ == "__main__":
    main()
