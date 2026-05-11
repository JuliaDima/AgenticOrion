"""
create_blind_packets.py

Generates anonymised BLIND versions of all 12 observation packets.

Strips everything that lets an LLM identify the object from training data:
  - All proper names (TNS names, catalogue IDs, host galaxy names)
  - Discovery papers (arXiv IDs, ADS links, TNS/WISeREP URLs)
  - Class-conclusory pipeline labels (FBOT_candidate, repeating_FRB, SN_Ia, ...)
  - source URLs and query_hints (contain object names)
  - fetch_log paths (contain object names)

Keeps all raw observational signal:
  - Modality, mission context
  - Physical measurements (redshift, DM, peak_mag, burst_rate, RM, distance)
  - Photometric/spectroscopic data files (light curves, cutouts, catalogues)
  - Observational labels (high_DM, ambiguous_class, confirmed_extragalactic, ...)

Output: packets/packet_NN_BLIND/packet.json  +  symlinks to original data files.
"""

import copy
import json
import os
import re
import shutil
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent
PACKETS_ROOT = REPO_ROOT / "packets"

# ── Labels that name or strongly hint at the astrophysical class ────────────
REMOVE_LABEL_PATTERNS = re.compile(
    r"FBOT|repeating_FRB|FRB|SN_Ia|SN_IIP|SN_Ib|LRD_candidate|"
    r"strong_lens|confirmed_strong|probable_strong|cosmological_probe|"
    r"early_universe|spectroscopic_confirmed|standard_plateau|"
    r"artefact|bogus|non_astrophysical|subtraction_artefact|"
    r"RFI_candidate|CTRL|reject|excluded",
    re.IGNORECASE,
)

# ── Keep these observational labels even if they partially match ─────────────
KEEP_LABEL_PATTERNS = re.compile(
    r"high_|low_|fast_|ambiguous|triage|follow_up|novelty|"
    r"confirmed_extragalactic|extreme_RM|high_z|unconfirmed|"
    r"grade_|broker_|multi_epoch|single_epoch|early_excess",
    re.IGNORECASE,
)


def _filter_labels(labels: list[str]) -> list[str]:
    kept = []
    for label in labels:
        if KEEP_LABEL_PATTERNS.search(label):
            kept.append(label)
        elif not REMOVE_LABEL_PATTERNS.search(label):
            kept.append(label)
    # Always keep at least one observational label so agents know what stream this is
    return kept if kept else ["observational_alert"]


def _scrub_ids(ids: dict, blind_id: str) -> dict:
    """Replace all name fields with blind ID; keep numeric observables."""
    NUMERIC_KEEP = {
        "RA_deg", "Dec_deg", "redshift", "host_redshift",
        "DM_pc_cm3", "discovery_MJD", "CHIME_detection_MJD",
    }
    out = {"blind_id": blind_id}
    for k, v in ids.items():
        if k in NUMERIC_KEEP:
            if v is None:
                continue
            # Jitter RA/Dec by a small random-looking but deterministic offset
            # so the coordinates don't directly identify the field
            if k == "RA_deg":
                out[k] = round(float(v) + 13.7, 4)
            elif k == "Dec_deg":
                out[k] = round(float(v) - 8.3, 4)
            else:
                out[k] = v
    return out


_NAME_PATTERN = re.compile(
    r"AT20\w+|FRB\s*\d+\w*|SN\s*20\d+\w*|JADES[-\s]?\d+|ATLAS\d+\w*|"
    r"EUCL_J[\d.+\-]+|EUC_J[\d.+\-]+|CGCG\s+[\d\-]+|SDSS\s+J\w+|"
    r"ZTF\d+\w*|WISeREP|ALeRCE|TNS\b|SIMBAD\b|CHIME\b",
    re.IGNORECASE,
)


def _scrub_summary(pkt: dict, blind_id: str) -> str:
    """
    Build a fresh observational description from metadata only.
    Never reuses the original summary (which names the object).
    """
    mission  = pkt.get("mission", "unknown mission")
    modality = ", ".join(pkt.get("modality", []))
    meta     = pkt.get("metadata", {})
    labels   = _filter_labels(pkt.get("initial_pipeline_labels", []))

    parts = [f"Observation from {mission}. Modalities: {modality}."]

    if meta.get("redshift"):
        parts.append(f"Redshift z={meta['redshift']}.")
    if meta.get("DM_pc_cm3"):
        parts.append(f"Dispersion measure DM={meta['DM_pc_cm3']} pc/cm³.")
    if meta.get("peak_mag_orange"):
        parts.append(f"Peak magnitude {meta['peak_mag_orange']} (orange band).")
    if meta.get("distance_Mpc"):
        parts.append(f"Distance ~{meta['distance_Mpc']} Mpc.")
    if meta.get("burst_rate_per_day"):
        parts.append(f"Burst rate {meta['burst_rate_per_day']}.")
    if meta.get("RM_rad_m2"):
        parts.append(f"Rotation measure {meta['RM_rad_m2']} rad/m².")
    if meta.get("scattering_500MHz_ms"):
        parts.append(f"Scattering time at 500 MHz: {meta['scattering_500MHz_ms']} ms.")
    if labels:
        parts.append(f"Pipeline flags: {', '.join(labels)}.")

    return " ".join(parts)


def _scrub_metadata(meta: dict) -> dict:
    """Keep physical numbers; strip paper IDs, host names, class debates."""
    REMOVE_KEYS = {
        "key_paper_arXiv", "class_debate", "host_galaxy",
        "discovery_survey",
    }
    out = {}
    for k, v in meta.items():
        if k in REMOVE_KEYS:
            continue
        out[k] = v
    return out


def make_blind_packet(src_dir: Path, blind_index: int) -> dict:
    pkt = json.loads((src_dir / "packet.json").read_text())
    blind_id = f"BLIND_{blind_index:02d}"

    blind = copy.deepcopy(pkt)

    # experiment type
    blind["experiment_type"] = "BLIND"

    # strip source URLs
    blind.pop("source", None)
    blind.pop("query_hints", None)
    blind.pop("fetch_log", None)
    blind.pop("small_data_product", None)

    # anonymise IDs
    blind["object_or_event_id"] = _scrub_ids(pkt.get("object_or_event_id", {}), blind_id)

    # build fresh observational summary (never reuses original which names the object)
    blind["short_summary"] = _scrub_summary(pkt, blind_id)

    # scrub metadata
    blind["metadata"] = _scrub_metadata(pkt.get("metadata", {}))

    # filter labels
    blind["initial_pipeline_labels"] = _filter_labels(pkt.get("initial_pipeline_labels", []))

    # keep populated_data_products as-is (points to real data files)
    # keep modality, mission

    return blind


def main() -> None:
    src_packets = sorted(PACKETS_ROOT.glob("packet_[0-9][0-9]_*/packet.json"))
    print(f"Found {len(src_packets)} source packets")

    created = []
    for src_json in src_packets:
        src_dir = src_json.parent
        # Extract index from directory name
        m = re.match(r"packet_(\d+)_", src_dir.name)
        if not m:
            continue
        idx = int(m.group(1))
        blind_dir = PACKETS_ROOT / f"packet_{idx:02d}_BLIND"
        blind_dir.mkdir(exist_ok=True)

        # Write blind packet.json
        blind_pkt = make_blind_packet(src_dir, idx)
        (blind_dir / "packet.json").write_text(
            json.dumps(blind_pkt, indent=2), encoding="utf-8"
        )

        # Symlink or copy data directory so agents can still read light curves
        src_data = src_dir / "data"
        dst_data = blind_dir / "data"
        if src_data.exists() and not dst_data.exists():
            # Use a real copy so the blind packet is fully self-contained
            shutil.copytree(src_data, dst_data)

        created.append(blind_dir.name)
        print(f"  {src_dir.name}  →  {blind_dir.name}  "
              f"labels={blind_pkt['initial_pipeline_labels']}")

    print(f"\nCreated {len(created)} BLIND packets in {PACKETS_ROOT}")
    print("Add them to observation_packets_registry.py with experiment_type='BLIND' to run.")


if __name__ == "__main__":
    main()
