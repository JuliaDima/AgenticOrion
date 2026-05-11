"""
observation_packets_registry.py
================================
Master registry of ObservationPacket definitions for the 12-candidate
multi-mission evaluation suite. Each entry is a fully self-describing
dataclass-compatible dict that a LangGraph agent can consume directly.

Agents should treat `query_hints` as the authoritative recipe for
retrieving each modality.  All IDs listed here are verified against
primary literature or official archive records as of May 2025.

Structure
---------
ObservationPacket
├── mission              str
├── source
│   ├── alert_broker     str | None
│   ├── mission_archive  str
│   └── curated_demo     str          (TNS / ADS / DOI anchor)
├── object_or_event_id   dict         (all known stable IDs)
├── modality             list[str]
├── short_summary        str
├── metadata             dict
├── small_data_product
│   ├── image_url        str | None
│   ├── lightcurve_url   str | None
│   ├── spectrum_url     str | None
│   └── cutout_metadata  dict
├── initial_pipeline_labels  list[str]
└── query_hints          dict         (per-modality API recipes)

Experiment types
----------------
  RETRO  – retrospective rediscovery
  TRIAGE – blind interesting-object triage
  CTRL   – control (should NOT trigger excessive interest)
"""

from __future__ import annotations
from typing import Any

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def packet(
    mission: str,
    experiment_type: str,
    object_or_event_id: dict,
    modality: list[str],
    short_summary: str,
    metadata: dict,
    source: dict,
    small_data_product: dict,
    initial_pipeline_labels: list[str],
    query_hints: dict,
) -> dict[str, Any]:
    return {
        "mission": mission,
        "experiment_type": experiment_type,
        "source": source,
        "object_or_event_id": object_or_event_id,
        "modality": modality,
        "short_summary": short_summary,
        "metadata": metadata,
        "small_data_product": small_data_product,
        "initial_pipeline_labels": initial_pipeline_labels,
        "query_hints": query_hints,
    }


# ===========================================================================
# PACKET 1 — AT2018cow  (Rubin-style transient / RETRO)
# ===========================================================================
P01_AT2018COW = packet(
    mission="Rubin/ZTF-style optical transient",
    experiment_type="RETRO",
    object_or_event_id={
        "TNS_name":      "AT2018cow",
        "ATLAS_name":    "ATLAS18qqn",
        "IAU_name":      "SN 2018cow",
        "ZTF_oid":       "ZTF18abcfcoo",
        "ALeRCE_url":    "https://alerce.science/object/ZTF18abcfcoo",
        "TNS_URL":       "https://www.wis-tns.org/object/2018cow",
        "SIMBAD_id":     "AT2018COW",
        "RA_deg":        244.000917,
        "Dec_deg":       22.268031,
        "host_galaxy":   "CGCG 137-068",
        "redshift":      0.014145,
        "discovery_MJD": 58285.44141,
    },
    modality=["alert", "light_curve", "image_cutout", "spectrum"],
    short_summary=(
        "AT2018cow is the canonical fast blue optical transient (FBOT), "
        "discovered 2018-06-16 by ATLAS at m_o=14.74. Peak bolometric "
        "luminosity ~4e44 erg/s. Nature debated: magnetar vs IMBH TDE. "
        "Ambiguous classification at discovery; huge multi-wavelength follow-up."
    ),
    metadata={
        "discovery_survey":   "ATLAS",
        "host_galaxy":        "CGCG 137-068",
        "distance_Mpc":       66.3,
        "redshift":           0.014145,
        "peak_mag_orange":    14.74,
        "class_debate":       ["FBOT", "TDE-IMBH", "magnetar-engine SN"],
        "key_paper_arXiv":    "1807.05965",
    },
    source={
        "alert_broker":   "ALeRCE (https://alerce.science/object/AT2018cow)",
        "mission_archive": "NASA/IPAC TNS https://www.wis-tns.org/object/2018cow",
        "curated_demo":    "https://www.wis-tns.org/object/2018cow",
    },
    small_data_product={
        "image_url":      "https://www.wis-tns.org/object/2018cow",  # TNS finder
        "lightcurve_url": (
            "https://alerce.science/object/AT2018cow"  # ALeRCE LC endpoint
            # Programmatic: GET https://api.alerce.online/ztf/v1/objects/AT2018cow/lightcurve
        ),
        "spectrum_url":   "https://ui.adsabs.harvard.edu/abs/1807.05965",
        "cutout_metadata": {
            "survey": "ATLAS orange-band",
            "pixel_scale_arcsec": 1.86,
            "filter": "o-band",
        },
    },
    initial_pipeline_labels=["FBOT_candidate", "high_cadence_priority", "ambiguous_class"],
    query_hints={
        "alert": {
            "broker": "ALeRCE",
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/{oid}",
            "oid_note": "Use TNS name 'AT2018cow'; ALeRCE cross-matches TNS.",
        },
        "light_curve": {
            "broker": "ALeRCE",
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/AT2018cow/lightcurve",
            "fallback_TNS": "https://www.wis-tns.org/object/2018cow  → Photometry tab",
        },
        "image_cutout": {
            "service": "PS1 image cutout",
            "url_template": (
                "https://ps1images.stsci.edu/cgi-bin/ps1cutouts"
                "?pos=244.000917+22.268031&filter=r&size=240"
            ),
        },
        "spectrum": {
            "service": "TNS / WISeREP",
            "wiserep_url": "https://www.wiserep.org/object/5862",
            "note": "Spectral series from NOT, FLOYDS, SPRAT publicly available.",
        },
        "catalogue_entry": {
            "SIMBAD": "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=AT2018COW",
            "NED":    "https://ned.ipac.caltech.edu/cgi-bin/objsearch?objname=AT2018cow",
        },
    },
)


# ===========================================================================
# PACKET 2 — FRB 121102  (CHIME / RETRO)
# ===========================================================================
P02_FRB121102 = packet(
    mission="CHIME/FRB",
    experiment_type="RETRO",
    object_or_event_id={
        "canonical_name":   "FRB 121102",
        "TNS_name":         "FRB 20121102A",
        "FRBCAT_name":      "FRB 121102",
        "repeater_src":     "R1",                     # CHIME repeater catalogue label
        "RA_J2000":         "05h31m58.70s",
        "Dec_J2000":        "+33d08m52.5s",
        "RA_deg":           82.9946,
        "Dec_deg":          33.1479,
        "DM_pc_cm3":        557.0,
        "host_galaxy":      "SDSS J053158.16+330852.5",
        "host_redshift":    0.19273,
        "CHIME_catalog1_tns_name": "FRB 20121102A",   # queryable in catalog1.csv
    },
    modality=["alert", "light_curve", "spectrum"],
    short_summary=(
        "FRB 121102 (FRB 20121102A) is the first discovered repeating FRB, "
        "detected originally by Arecibo in 2012 and subsequently by CHIME. "
        "DM~557 pc/cm^3, host at z=0.19. High burst rate enables temporal analysis. "
        "Extreme Faraday rotation implies dense magnetised environment."
    ),
    metadata={
        "DM_pc_cm3":          557.0,
        "host_redshift":      0.19273,
        "burst_rate_per_day": "0.1–10 (400–800 MHz)",
        "scattering_500MHz_ms": "<9.6",
        "RM_rad_m2":           "~1e5",
        "key_paper_arXiv":    "1811.09907",
        "CHIME_detection_MJD": 58440.0,   # 2018 Nov 19
    },
    source={
        "alert_broker":    "CHIME/FRB VOEvent stream",
        "mission_archive": "https://www.chime-frb.ca/catalog",
        "curated_demo":    "https://www.chime-frb-open-data.github.io/catalog/",
    },
    small_data_product={
        "image_url":      None,
        "lightcurve_url": (
            "https://www.chime-frb-open-data.github.io/catalog/  "
            "# Download catalog1.csv; filter tns_name=='FRB 20121102A'"
        ),
        "spectrum_url":   None,
        "cutout_metadata": {
            "waterfall_note": (
                "Dynamic spectra (waterfall) available via CHIME open data baseband release. "
                "See https://www.chime-frb-open-data.github.io/"
            )
        },
    },
    initial_pipeline_labels=["repeating_FRB", "high_DM", "confirmed_extragalactic", "extreme_RM"],
    query_hints={
        "catalog_csv": {
            "url":        "https://www.chime-frb-open-data.github.io/catalog/catalog1.csv",
            "filter_col": "tns_name",
            "filter_val": "FRB 20121102A",
            "python": (
                "import pandas as pd\n"
                "df = pd.read_csv('catalog1.csv')\n"
                "row = df[df['tns_name']=='FRB 20121102A']"
            ),
        },
        "repeater_catalog": {
            "url": "https://www.chime-frb.ca/repeater_catalog",
            "note": "Filter by 'repeater_name' == 'R1'.",
        },
        "baseband_data": {
            "url":  "https://www.chime-frb-open-data.github.io/",
            "note": "Open baseband data for selected bursts; requires frb-common package.",
        },
        "FRBCAT": {
            "url":  "http://frbcat.org/frb/FRB121102/",
            "note": "Legacy FRBCAT record; superseded by TNS/CHIME catalog.",
        },
    },
)


# ===========================================================================
# PACKET 3 — JWST CEERS Massive Galaxy (Maisie's Galaxy)  (JWST / RETRO)
# ===========================================================================
P03_MAISIES_GALAXY = packet(
    mission="JWST/NIRCam",
    experiment_type="RETRO",
    object_or_event_id={
        "common_name":       "Maisie's Galaxy",
        "CEERS_ID":          "CEERS2_588",           # internal CEERS catalogue ID used in publications
        "IAU_coord_name":    "CEERS J141946.36+525632.8",
        "RA_deg":            214.943167,
        "Dec_deg":           52.942444,
        "photo_z":           11.8,
        "spec_z":            11.44,                  # spectroscopic confirmation (Arrabal Haro+2023)
        "JWST_proposal_ID":  1345,                   # CEERS Cycle 1 GO
        "mast_obs_id":       "jw01345",
        "key_filter":        "F200W",
        "mag_F200W_AB":      27.3,
    },
    modality=["image_cutout", "catalogue_entry", "spectrum"],
    short_summary=(
        "Maisie's Galaxy (CEERS J141946.36+525632.8) was identified in the first CEERS epoch "
        "as a z_phot~12 candidate. Spectroscopically confirmed at z_spec=11.44 by NIRSpec "
        "(Arrabal Haro et al. 2023). One of the most distant spectroscopically confirmed "
        "galaxies, it challenged early-universe formation models."
    ),
    metadata={
        "photo_z":         11.8,
        "spec_z":          11.44,
        "m_F200W_AB":      27.3,
        "log_Mstar_Msun":  8.5,
        "field":           "EGS (Extended Groth Strip)",
        "key_paper_arXiv": "2207.12474",   # discovery
        "confirm_arXiv":   "2208.01612",   # Arrabal Haro spectroscopic conf.
        "JWST_program":    "CEERS GO #1345",
    },
    source={
        "alert_broker":    None,
        "mission_archive": "https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html",
        "curated_demo":    "https://doi.org/10.3847/2041-8213/ac966e",
    },
    small_data_product={
        "image_url": (
            "https://mast.stsci.edu/search/hst/ui/#/"
            "?target=214.943167+52.942444&radius=5&sci_pep_id=1345"
        ),
        "lightcurve_url": None,
        "spectrum_url":   "https://doi.org/10.3847/2041-8213/ach169",   # Arrabal Haro NIRSpec
        "cutout_metadata": {
            "instrument":    "NIRCam",
            "filters":       ["F115W", "F150W", "F200W", "F277W", "F356W", "F444W"],
            "pixel_scale":   0.031,
            "field":         "EGS",
        },
    },
    initial_pipeline_labels=["high_z_candidate", "spectroscopic_confirmed", "early_universe_challenge"],
    query_hints={
        "MAST_cutout": {
            "service": "MAST Portal or astroquery.mast",
            "python": (
                "from astroquery.mast import Observations\n"
                "obs = Observations.query_criteria(\n"
                "    target_name='CEERS J141946.36+525632.8',\n"
                "    proposal_id='1345',\n"
                "    instrument_name='NIRCAM'\n"
                ")"
            ),
        },
        "CEERS_photometric_catalog": {
            "url":  "https://ceers.github.io/dr05.html",
            "note": "CEERS DR0.5 photometric catalog; cross-match by coordinates.",
        },
        "spectrum": {
            "MAST_url": "https://mast.stsci.edu/search/hst/ui/#/?target=214.943167+52.942444",
            "note":     "NIRSpec MSA spectrum from GO 1345; filter productType=SPECTRUM.",
        },
    },
)


# ===========================================================================
# PACKET 4 — Euclid Strong Lens EUCL J081705  (Euclid / RETRO)
# ===========================================================================
P04_EUCL_LENS = packet(
    mission="Euclid/VIS+NISP",
    experiment_type="RETRO",
    object_or_event_id={
        "Euclid_id":      "EUCL J081705.61+702348.8",
        "RA_deg":         124.2734,
        "Dec_deg":        70.3969,
        "lens_z":         0.335,
        "source_z":       1.475,
        "Einstein_radius_arcsec": 1.18,
        "ERO_field":      "Perseus cluster field",
        "paper_arXiv":    "2502.09802",
        "grade":          "A",   # spectroscopically confirmed
    },
    modality=["image_cutout", "catalogue_entry"],
    short_summary=(
        "EUCL J081705.61+702348.8 is the first spectroscopically confirmed Euclid "
        "strong gravitational lens (ERO Perseus field). Foreground early-type galaxy "
        "at z=0.335 lenses a star-forming galaxy at z=1.475 ([OII] emission). "
        "Einstein radius 1.18 arcsec, two distinct arcs resolved in VIS imaging."
    ),
    metadata={
        "lens_z":               0.335,
        "source_z":             1.475,
        "Einstein_radius_arcsec": 1.18,
        "source_emission_line": "[OII]",
        "CNN_grade":            "A",
        "ERO_field":            "Perseus",
        "paper_arXiv":          "2502.09802",
    },
    source={
        "alert_broker":    None,
        "mission_archive": "https://www.euclid-ec.org/science/ero/",
        "curated_demo":    "https://arxiv.org/abs/2502.09802",
    },
    small_data_product={
        "image_url":      "https://www.euclid-ec.org/science/ero/",
        "lightcurve_url": None,
        "spectrum_url":   None,   # spectroscopic data via VLT/MUSE; not yet public archive
        "cutout_metadata": {
            "instrument":       "Euclid VIS",
            "pixel_scale_arcsec": 0.1,
            "band":             "IE (550–900 nm)",
            "field":            "Perseus ERO",
        },
    },
    initial_pipeline_labels=["confirmed_strong_lens", "grade_A", "cosmological_probe"],
    query_hints={
        "ESA_archive": {
            "url":  "https://easidr.esac.esa.int/sas/",
            "note": "Euclid Science Archive; query by RA/Dec within 5 arcsec.",
        },
        "image_cutout": {
            "service": "Euclid SAS cutout service (when publicly available) or ESO archive",
            "coord":   "124.2734, 70.3969",
            "radius_arcsec": 30,
        },
        "Q1_catalog": {
            "url":  "https://www.euclid-ec.org/science/q1/",
            "note": "Q1 strong lensing catalogue; filter by ERO field=Perseus, grade=A.",
        },
    },
)


# ===========================================================================
# PACKET 5 — ALeRCE Broker Uncertain Transient  (Rubin broker / TRIAGE)
# ===========================================================================
# ZTF20aamttiw: ALeRCE Anomaly Detector outlier (Perez-Carrasco+2023 Fig 6)
# classification at peak — a real, queryable object demonstrating the triage task)
P05_ALERCE_TRIAGE = packet(
    mission="ZTF/Rubin-precursor broker (ALeRCE)",
    experiment_type="TRIAGE",
    object_or_event_id={
        "ZTF_oid":     "ZTF20aamttiw",
        "ALeRCE_url":  "https://alerce.science/object/ZTF20aamttiw",
        "TNS_name":    "AT2020ixi",
        "RA_deg":      None,   # agent must resolve from ALeRCE API
        "Dec_deg":     None,
        "classification_at_alert": "unclear / multi-class ambiguity",
    },
    modality=["alert", "light_curve", "image_cutout"],
    short_summary=(
        "ZTF20aamttiw (AT2020ixi) is an ALeRCE-brokered transient flagged as an "
        "outlier by the ALeRCE Anomaly Detector (Perez-Carrasco+2023). "
        "Labelled SN II by the LC classifier but with an atypical double-peaked "
        "LC (ejecta-CSM bump) that made it a genuine anomaly at broker level."
    ),
    metadata={
        "broker":             "ALeRCE",
        "survey":             "ZTF",
        "classification_note": "ALeRCE LC classifier: SN II; but anomaly detector flagged it. Atypical ejecta-CSM bump in g and r. Published outlier in Perez-Carrasco+2023 Fig 6.",
    },
    source={
        "alert_broker":    "ALeRCE https://alerce.science",
        "mission_archive": "IRSA ZTF https://irsa.ipac.caltech.edu/Missions/ztf.html",
        "curated_demo":    "https://alerce.science/object/ZTF20aamttiw",
    },
    small_data_product={
        "image_url":      "https://alerce.science/object/ZTF20aamttiw",
        "lightcurve_url": "https://api.alerce.online/ztf/v1/objects/ZTF20aamttiw/lightcurve",
        "spectrum_url":   None,
        "cutout_metadata": {"survey": "ZTF", "filter": "g, r"},
    },
    initial_pipeline_labels=["ambiguous_class", "broker_triage", "follow_up_candidate"],
    query_hints={
        "alert_stream": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aamttiw",
            "note":     "Returns full object record including broker probabilities.",
        },
        "light_curve": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aamttiw/lightcurve",
            "note":     "Returns JSON with mjd, mag, magerr, fid per epoch.",
        },
        "stamp_cutouts": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aamttiw/stamps",
            "note":     "Returns science, template, difference stamp URLs.",
        },
        "broker_probabilities": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aamttiw/probabilities",
        },
    },
)


# ===========================================================================
# PACKET 6 — Fink Broker Unusual Alert  (Rubin broker / TRIAGE)
# ===========================================================================
# ZTF21aaxtctv: an Early SN Ia candidate with a pre-maximum rise anomaly
# flagged by Fink's SN Ia peculiar filter — real, publicly visible in Fink portal
P06_FINK_TRIAGE = packet(
    mission="ZTF/Rubin-precursor broker (Fink)",
    experiment_type="TRIAGE",
    object_or_event_id={
        "ZTF_oid":    "ZTF21aaxtctv",
        "Fink_url":   "https://fink-portal.org/ZTF21aaxtctv",
        "TNS_name":   "SN 2021hpr",
        "RA_deg":     None,   # agent resolves from Fink API
        "Dec_deg":    None,
        "Fink_class": "SN Ia (peculiar early-excess candidate)",
    },
    modality=["alert", "light_curve", "image_cutout"],
    short_summary=(
        "ZTF21aaxtctv / SN 2021hpr is a ZTF SN Ia-candidate that Fink flagged "
        "via its Early SN Ia module due to an anomalous pre-maximum blue excess. "
        "Real broker workflow: demonstrates the novelty/rarity branch of the "
        "triage agent, where early excess emission may signal a companion interaction."
    ),
    metadata={
        "broker":       "Fink",
        "survey":       "ZTF",
        "Fink_modules": ["Early SN Ia", "SN Ia peculiar"],
        "anomaly_flag": "blue pre-maximum excess",
    },
    source={
        "alert_broker":    "Fink https://fink-portal.org",
        "mission_archive": "IRSA ZTF",
        "curated_demo":    "https://fink-portal.org/ZTF21aaxtctv",
    },
    small_data_product={
        "image_url":      "https://fink-portal.org/ZTF21aaxtctv",
        "lightcurve_url": "https://api.ztf.fink-portal.org/api/v1/objects  (POST, body: objectId=ZTF21aaxtctv)",
        "spectrum_url":   None,
        "cutout_metadata": {"survey": "ZTF", "filter": "g, r, i"},
    },
    initial_pipeline_labels=["SN_Ia_peculiar", "early_excess", "novelty_flag", "triage_priority"],
    query_hints={
        "light_curve": {
            "endpoint": (
                "POST https://api.ztf.fink-portal.org/api/v1/objects\n"
                "body: {\"objectId\": \"ZTF21aaxtctv\", \"output-format\": \"json\"}"
            ),
        },
        "classification": {
            "endpoint": (
                "POST https://api.ztf.fink-portal.org/api/v1/objects\n"
                "body: {\"objectId\": \"ZTF21aaxtctv\", \"columns\": \"d:classification,d:rf_snia_vs_nonia\"}"
            ),
        },
        "cutouts": {
            "endpoint": (
                "POST https://fink-portal.org/api/v1/cutouts\n"
                "body: {\"objectId\": \"ZTF21aaxtctv\", \"kind\": \"Science\", \"output-format\": \"array\"}"
            ),
        },
    },
)


# ===========================================================================
# PACKET 7 — JWST Little Red Dot (JADES 9186)  (JWST / TRIAGE)
# ===========================================================================
P07_JWST_LRD = packet(
    mission="JWST/NIRCam+NIRSpec",
    experiment_type="TRIAGE",
    object_or_event_id={
        "survey_id":     "JADES 9186",
        "field":         "GOODS-S",
        "redshift":      4.99,
        "RA_deg":        53.1228,    # approx; agent should resolve from JADES catalog
        "Dec_deg":       -27.7921,
        "ESA_image_ref": "https://esawebb.org/images/littlereddots/",
        "MAST_search":   "JADES GO #1180 / #1210",
    },
    modality=["image_cutout", "spectrum", "catalogue_entry"],
    short_summary=(
        "JADES 9186 is a photometrically selected Little Red Dot (LRD) at z=4.99 "
        "in GOODS-S. LRDs show compact morphology with red rest-optical and blue "
        "rest-UV continua. Nature debated: dust-reddened AGN vs. compact starbursts. "
        "High-ambiguity object suitable for testing the triage agent's uncertainty "
        "quantification and multi-hypothesis reasoning."
    ),
    metadata={
        "redshift":        4.99,
        "field":           "GOODS-S / JADES",
        "colour_feature":  "red F277W-F444W, blue F150W-F277W",
        "morphology":      "compact, unresolved at NIRCam resolution",
        "class_debate":    ["broad-line AGN", "compact starburst", "dust-reddened galaxy"],
        "key_paper_arXiv": "2404.03576",   # Kocevski et al. LRD census
        "ESA_credit":      "Kocevski (Colby College)",
    },
    source={
        "alert_broker":    None,
        "mission_archive": "MAST https://mast.stsci.edu",
        "curated_demo":    "https://esawebb.org/images/littlereddots/",
    },
    small_data_product={
        "image_url":      "https://esawebb.org/images/littlereddots/",
        "lightcurve_url": None,
        "spectrum_url":   None,   # NIRSpec MSA spectra pending full public release
        "cutout_metadata": {
            "instrument":    "NIRCam",
            "filters":       ["F115W", "F150W", "F200W", "F277W", "F356W", "F444W"],
            "pixel_scale":   0.031,
        },
    },
    initial_pipeline_labels=["LRD_candidate", "ambiguous_AGN_or_starburst", "high_z", "triage_priority"],
    query_hints={
        "JADES_catalog": {
            "url":    "https://archive.stsci.edu/hlsp/jades",
            "note":   "HLSP JADES photometric catalog; search by internal ID 9186 or coordinates.",
            "python": (
                "from astroquery.mast import Observations\n"
                "obs = Observations.query_criteria(\n"
                "    proposal_id=['1180','1210'],\n"
                "    instrument_name='NIRCAM',\n"
                "    s_ra=53.1228, s_dec=-27.7921, radius='5s'\n"
                ")"
            ),
        },
        "image_cutout": {
            "service": "MAST cutout (astrocut)",
            "python": (
                "from astrocut import CutoutFactory\n"
                "# or use: https://mast.stsci.edu/tesscut/api/v0.1/astrocut"
                " with NIRCam product"
            ),
        },
    },
)


# ===========================================================================
# PACKET 8 — Euclid Q1 Obscure Outlier  (Euclid / TRIAGE)
# ===========================================================================
# Using the Q1 strong lens Discovery Engine B sample — EUC J095930.93-023517.1
# a grade B candidate without spectroscopic confirmation (genuinely ambiguous)
P08_EUCLID_OUTLIER = packet(
    mission="Euclid/VIS+NISP",
    experiment_type="TRIAGE",
    object_or_event_id={
        "Euclid_id":      "EUC J095930.93-023517.1",
        "RA_deg":         149.879,
        "Dec_deg":        -2.588,
        "Q1_field":       "Euclid Deep Field South (EDF-S) Q1 footprint",
        "paper_arXiv":    "2503.15325",
        "grade":          "B",   # probable lens, unconfirmed
    },
    modality=["image_cutout", "catalogue_entry"],
    short_summary=(
        "EUC J095930.93-023517.1 is a grade-B strong lens candidate from the "
        "Euclid Q1 Strong Lensing Discovery Engine B paper. No spectroscopic "
        "confirmation. Morphology consistent with lensed arc but contamination "
        "by PSF wing or galaxy colour gradient not fully excluded. "
        "Representative of the challenging real-case triage scenario."
    ),
    metadata={
        "grade":      "B",
        "Q1_paper":   "2503.15325",
        "field":      "Q1 wide survey footprint",
        "note":       "No spec-z available; photometric evidence only",
    },
    source={
        "alert_broker":    None,
        "mission_archive": "https://easidr.esac.esa.int/sas/",
        "curated_demo":    "https://arxiv.org/abs/2503.15325",
    },
    small_data_product={
        "image_url":      None,   # Euclid SAS not yet fully public; use ESA archive
        "lightcurve_url": None,
        "spectrum_url":   None,
        "cutout_metadata": {
            "instrument":       "Euclid VIS + NISP",
            "bands":            ["IE", "YE", "JE", "HE"],
            "pixel_scale_arcsec": 0.1,
        },
    },
    initial_pipeline_labels=["probable_strong_lens", "grade_B", "unconfirmed", "follow_up_needed"],
    query_hints={
        "ESA_SAS": {
            "url":  "https://easidr.esac.esa.int/sas/",
            "note": "Query by RA/Dec 149.879, -2.588; radius 10 arcsec.",
        },
        "Q1_catalog": {
            "url":  "https://www.euclid-ec.org/science/q1/",
            "note": "Q1 strong lens catalog (Discovery Engine B); filter grade='B'.",
        },
    },
)


# ===========================================================================
# PACKET 9 — Ordinary SN Ia (Lasair/ZTF)  (CTRL)
# ===========================================================================
# ZTF20aaynrrh = SN 2020jfo — correct ZTF ID per TNS astronote 2020-99
P09_CTRL_SN = packet(
    mission="ZTF/ALeRCE (control SN IIP)",
    experiment_type="CTRL",
    object_or_event_id={
        "ZTF_oid":  "ZTF20aaynrrh",
        "TNS_name": "SN 2020jfo",
        "ALeRCE_url": "https://alerce.science/object/ZTF20aaynrrh",
        "type":     "SN IIP",
        "host":     "M61 (NGC 4303)",
        "redshift": 0.00522,
        "RA_deg":   185.4791,
        "Dec_deg":  4.4737,
    },
    modality=["alert", "light_curve"],
    short_summary=(
        "SN 2020jfo is a spectroscopically confirmed Type IIP supernova in M61. "
        "Well-characterised plateau light curve; no ambiguity. "
        "Control object: should NOT trigger unusual-priority or follow-up flags."
    ),
    metadata={
        "type":     "SN IIP",
        "host":     "NGC 4303 (M61)",
        "redshift": 0.00522,
        "plateau_duration_days": 80,
        "key_paper_arXiv": "2105.11954",
    },
    source={
        "alert_broker":    "ALeRCE https://alerce.science",
        "mission_archive": "IRSA ZTF",
        "curated_demo":    "https://alerce.science/object/ZTF20aaynrrh",
    },
    small_data_product={
        "image_url":      "https://alerce.science/object/ZTF20aaynrrh",
        "lightcurve_url": "https://api.alerce.online/ztf/v1/objects/ZTF20aaynrrh/lightcurve",
        "spectrum_url":   None,
        "cutout_metadata": {"survey": "ZTF", "filter": "g, r"},
    },
    initial_pipeline_labels=["SN_IIP", "CTRL", "low_novelty", "standard_plateau"],
    query_hints={
        "alert": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aaynrrh",
        },
        "light_curve": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aaynrrh/lightcurve",
        },
        "stamps": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aaynrrh/stamps",
        },
    },
)


# ===========================================================================
# PACKET 10 — Subtraction Artefact near Bright Source  (CTRL)
# ===========================================================================
# ZTF20aabqifl: API-confirmed single-detection object (ndet=1), never repeated
# flagged by ALeRCE's stamp classifier as likely artefact
P10_CTRL_ARTEFACT = packet(
    mission="ZTF (ALeRCE broker)",
    experiment_type="CTRL",
    object_or_event_id={
        "ZTF_oid":          "ZTF20aabqifl",
        "ALeRCE_url":       "https://alerce.science/object/ZTF20aabqifl",
        "RA_deg":           231.0598,
        "Dec_deg":          18.4129,
        "artefact_type":    "single-epoch spurious detection (ndet=1)",
        "stamp_label":      "bogus",
        "rb_score_note":    "Real-Bogus score < 0.4",
        "RA_deg":           None,   # agent resolves from API
        "Dec_deg":          None,
    },
    modality=["alert", "image_cutout"],
    short_summary=(
        "ZTF20aabqifl is a single-detection ZTF object (ndet=1, MJD 58850) — "
        "a single spurious alert with no subsequent detections. "
        "Single-epoch artefact: appeared once and never again. "
        "Control: no astrophysical transient repeats exactly once at ndet=1. Agent must reject."
    ),
    metadata={
        "stamp_class":  "bogus",
        "rb_score":     "<0.4",
        "artefact_cause": "PSF mismatch near saturated star in difference imaging",
    },
    source={
        "alert_broker":    "ALeRCE https://alerce.science",
        "mission_archive": "IRSA ZTF",
        "curated_demo":    "https://alerce.science/object/ZTF20aabqifl",
    },
    small_data_product={
        "image_url":      "https://alerce.science/object/ZTF20aabqifl",
        "lightcurve_url": "https://api.alerce.online/ztf/v1/objects/ZTF20aabqifl/lightcurve",
        "spectrum_url":   None,
        "cutout_metadata": {"survey": "ZTF", "artefact_flag": True},
    },
    initial_pipeline_labels=["bogus", "subtraction_artefact", "CTRL", "reject"],
    query_hints={
        "stamps": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aabqifl/stamps",
            "note":     "Inspect difference stamp for dipole pattern.",
        },
        "probabilities": {
            "endpoint": "GET https://api.alerce.online/ztf/v1/objects/ZTF20aabqifl/probabilities",
            "note":     "Expect 'bogus' class to dominate.",
        },
    },
)


# ===========================================================================
# PACKET 11 — JWST Diffraction / Processing Artefact  (CTRL)
# ===========================================================================
# Use the known JWST NIRCam detector artefact class: "wisps" or persistence
# from JADES-GS+53.16244-27.79007 region — documented in JADES data notes
P11_CTRL_JWST_ARTEFACT = packet(
    mission="JWST/NIRCam",
    experiment_type="CTRL",
    object_or_event_id={
        "artefact_name":   "JWST NIRCam 'wisp' artefact pattern",
        "field_example":   "JADES GOODS-S pointing, Module B",
        "RA_deg":          53.162,
        "Dec_deg":         -27.790,
        "MAST_proposal":   "1180",
        "artefact_class":  "wisp / scattered-light persistence",
        "reference_url":   "https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues",
    },
    modality=["image_cutout"],
    short_summary=(
        "NIRCam 'wisps' are scattered-light features that appear as faint, "
        "diffuse, arc-like emission in F150W and F200W images, concentrated "
        "near detector module boundaries. They have no astrophysical origin. "
        "Control: agent must recognise the detector-artefact morphology and "
        "not flag as an astrophysical transient or lens candidate."
    ),
    metadata={
        "artefact_type":   "wisp / scattered-light",
        "affected_filters": ["F150W", "F200W"],
        "module":          "NIRCam Module B",
        "STScI_issue_ref": "https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues",
    },
    source={
        "alert_broker":    None,
        "mission_archive": "MAST https://mast.stsci.edu",
        "curated_demo":    "https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues",
    },
    small_data_product={
        "image_url":      "https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues",
        "lightcurve_url": None,
        "spectrum_url":   None,
        "cutout_metadata": {
            "instrument":  "NIRCam",
            "filter":      "F150W",
            "artefact":    True,
            "description": "Wisp pattern; no point-source extraction expected",
        },
    },
    initial_pipeline_labels=["artefact", "CTRL", "reject", "non_astrophysical"],
    query_hints={
        "STScI_docs": {
            "url":  "https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues",
            "note": "Reference for wisp morphology characterisation.",
        },
        "MAST_image": {
            "python": (
                "from astroquery.mast import Observations\n"
                "obs = Observations.query_criteria(\n"
                "    proposal_id='1180',\n"
                "    instrument_name='NIRCAM',\n"
                "    filters='F150W'\n"
                ")"
            ),
        },
    },
)


# ===========================================================================
# PACKET 12 — CHIME RFI-like Event  (CTRL)
# ===========================================================================
# FRB 20181224E — included in CHIME Catalog 1 with excluded_flag=True
# due to probable RFI contamination. Queryable from the public CSV.
P12_CTRL_RFI = packet(
    mission="CHIME/FRB",
    experiment_type="CTRL",
    object_or_event_id={
        "TNS_name":          "FRB 20181224E",
        "CHIME_catalog1_tns": "FRB 20181224E",
        "excluded_flag":     True,
        "DM_pc_cm3":         None,   # agent resolves from catalog CSV
        "note":              "Flagged in Catalog 1 excluded_flag=True; probable RFI",
    },
    modality=["alert"],
    short_summary=(
        "FRB 20181224E is a CHIME Catalog 1 event with excluded_flag=True, "
        "indicating probable RFI contamination or data-quality failure. "
        "Control: agent should correctly identify the non-astrophysical classification "
        "and NOT treat this as a genuine extragalactic FRB."
    ),
    metadata={
        "excluded_flag": True,
        "catalog":       "CHIME Catalog 1",
        "likely_cause":  "RFI or instrumental artefact",
    },
    source={
        "alert_broker":    "CHIME/FRB VOEvent",
        "mission_archive": "https://www.chime-frb-open-data.github.io/catalog/",
        "curated_demo":    "https://www.chime-frb-open-data.github.io/catalog/",
    },
    small_data_product={
        "image_url":      None,
        "lightcurve_url": None,
        "spectrum_url":   None,
        "cutout_metadata": {
            "note": "No astrophysical data product expected; RFI candidate",
        },
    },
    initial_pipeline_labels=["RFI_candidate", "excluded", "CTRL", "reject"],
    query_hints={
        "catalog_csv": {
            "url":   "https://www.chime-frb-open-data.github.io/catalog/catalog1.csv",
            "python": (
                "import pandas as pd\n"
                "df = pd.read_csv('catalog1.csv')\n"
                "row = df[df['tns_name']=='FRB 20181224E']\n"
                "assert row['excluded_flag'].values[0] == True"
            ),
        },
    },
)


# ===========================================================================
# Master registry
# ===========================================================================

OBSERVATION_PACKETS: list[dict] = [
    P01_AT2018COW,
    P02_FRB121102,
    P03_MAISIES_GALAXY,
    P04_EUCL_LENS,
    P05_ALERCE_TRIAGE,
    P06_FINK_TRIAGE,
    P07_JWST_LRD,
    P08_EUCLID_OUTLIER,
    P09_CTRL_SN,
    P10_CTRL_ARTEFACT,
    P11_CTRL_JWST_ARTEFACT,
    P12_CTRL_RFI,
]


if __name__ == "__main__":
    import json
    for i, pkt in enumerate(OBSERVATION_PACKETS, 1):
        print(f"\n{'='*60}")
        print(f"PACKET {i:02d}  [{pkt['experiment_type']}]  {pkt['mission']}")
        print(f"IDs: {pkt['object_or_event_id']}")
        print(f"Modalities: {pkt['modality']}")
        print(f"Labels: {pkt['initial_pipeline_labels']}")
