# Observation Packets

---

## Reading this document

Each row gives:

- **Stable object ID(s)** — the string(s) a Python script or LLM should query
- **Primary archive URL** — direct, not a catalogue homepage
- **Programmatic API endpoint** — the exact call an agent should make
- **Notes on ambiguity / caveats**

---

## Packet 01 — AT2018cow [RETRO | Rubin-style transient]

| Field                | Value                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------- |
| TNS name             | `AT2018cow`                                                                                 |
| ATLAS internal name  | `ATLAS18qqn`                                                                                |
| IAU name             | `SN 2018cow`                                                                                |
| TNS direct URL       | https://www.wis-tns.org/object/2018cow                                                      |
| SIMBAD ID            | `AT2018COW`                                                                                 |
| RA, Dec (J2000, deg) | 244.000917, +22.268031                                                                      |
| Redshift             | 0.014145                                                                                    |
| Discovery MJD        | 58285.44                                                                                    |
| Host galaxy          | `CGCG 137-068`                                                                              |
| ALeRCE API           | `GET https://api.alerce.online/ztf/v1/objects/AT2018cow`                                    |
| ALeRCE LC            | `GET https://api.alerce.online/ztf/v1/objects/AT2018cow/lightcurve`                         |
| PS1 cutout           | `https://ps1images.stsci.edu/cgi-bin/ps1cutouts?pos=244.000917+22.268031&filter=r&size=240` |
| WISeREP spectra      | https://www.wiserep.org/object/5862                                                         |
| Key paper            | arXiv:1807.05965                                                                            |

**Caveat**: AT2018cow predates ZTF; ALeRCE cross-matches the TNS name.
Use the TNS JSON API (`https://www.wis-tns.org/api/get/object?name=2018cow&api_key=KEY`) for full photometry.

---

## Packet 02 — FRB 121102 / FRB 20121102A [RETRO | CHIME]

| Field                       | Value                                                                    |
| --------------------------- | ------------------------------------------------------------------------ |
| Canonical name              | `FRB 121102`                                                             |
| TNS / CHIME catalog name    | `FRB 20121102A`                                                          |
| CHIME repeater label        | `R1`                                                                     |
| RA, Dec (deg)               | 82.9946, +33.1479                                                        |
| DM (pc/cm³)                 | 557.0                                                                    |
| Host galaxy redshift        | 0.19273                                                                  |
| Catalog CSV                 | `https://www.chime-frb-open-data.github.io/catalog/catalog1.csv`         |
| CSV filter                  | `df[df['tns_name']=='FRB 20121102A']`                                    |
| Repeater catalog            | https://www.chime-frb.ca/repeater_catalog (filter `repeater_name`==`R1`) |
| FRBCAT legacy               | http://frbcat.org/frb/FRB121102/                                         |
| CHIME open data             | https://www.chime-frb-open-data.github.io/                               |
| Key paper (CHIME detection) | arXiv:1811.09907                                                         |

**Caveat**: FRB 121102 was discovered by Arecibo, not CHIME.
The CHIME catalog entry for `FRB 20121102A` covers the 2018 Nov 19 burst.
For full burst history, use the FRBCAT or CHIME open data baseband releases.

---

## Packet 03 — Maisie's Galaxy (CEERS) [RETRO | JWST]

| Field                      | Value                                                                                                                      |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Common name                | Maisie's Galaxy                                                                                                            |
| IAU coordinate name        | `CEERS J141946.36+525632.8`                                                                                                |
| CEERS catalog ID           | `CEERS2_588` (internal; used in Finkelstein+2022)                                                                          |
| RA, Dec (deg)              | 214.943167, +52.942444                                                                                                     |
| Photometric redshift       | 11.8                                                                                                                       |
| Spectroscopic redshift     | 11.44 (Arrabal Haro et al. 2023, arXiv:2208.01612)                                                                         |
| JWST proposal              | GO #1345 (CEERS)                                                                                                           |
| MAST search                | `https://mast.stsci.edu` → proposal_id=1345, instrument=NIRCAM                                                             |
| astroquery call            | `Observations.query_criteria(proposal_id='1345', instrument_name='NIRCAM', s_ra=214.943167, s_dec=52.942444, radius='5s')` |
| CEERS photometric catalog  | https://ceers.github.io/dr05.html                                                                                          |
| Key paper (discovery)      | arXiv:2207.12474                                                                                                           |
| Key paper (spec. confirm.) | arXiv:2208.01612                                                                                                           |

---

## Packet 04 — Euclid Strong Lens EUCL J081705 [RETRO | Euclid ERO]

| Field                    | Value                            |
| ------------------------ | -------------------------------- |
| Euclid ID                | `EUCL J081705.61+702348.8`       |
| RA, Dec (deg)            | 124.2734, +70.3969               |
| Lens redshift            | 0.335                            |
| Source redshift          | 1.475                            |
| Einstein radius (arcsec) | 1.18 ± 0.03                      |
| Confirmation grade       | A (spectroscopic)                |
| ERO field                | Perseus                          |
| ESA archive              | https://easidr.esac.esa.int/sas/ |
| Key paper                | arXiv:2502.09802                 |

**Caveat**: Euclid SAS public access is rolling out.
For now, use the ESA ERO data portal: https://www.euclid-ec.org/science/ero/
Image products for the Perseus field are available via DOI in the paper.

---

## Packet 05 — ALeRCE Triage (ZTF18acmzpls / AT2018lqh) [TRIAGE | Rubin broker]

| Field               | Value                                                                     |
| ------------------- | ------------------------------------------------------------------------- |
| ZTF object ID       | `ZTF18acmzpls`                                                            |
| TNS name            | `AT2018lqh`                                                               |
| ALeRCE URL          | https://alerce.science/object/ZTF18acmzpls                                |
| Object metadata     | `GET https://api.alerce.online/ztf/v1/objects/ZTF18acmzpls`               |
| Light curve         | `GET https://api.alerce.online/ztf/v1/objects/ZTF18acmzpls/lightcurve`    |
| Stamp cutouts       | `GET https://api.alerce.online/ztf/v1/objects/ZTF18acmzpls/stamps`        |
| Class probabilities | `GET https://api.alerce.online/ztf/v1/objects/ZTF18acmzpls/probabilities` |

**Design note**: This object was chosen because it has a multi-class probability
vector without a dominant winner at peak, forcing the agent to reason under uncertainty.

---

## Packet 06 — Fink Triage (ZTF21aaxtctv / SN 2021hpr) [TRIAGE | Rubin broker]

| Field           | Value                                                                                                                      |
| --------------- | -------------------------------------------------------------------------------------------------------------------------- |
| ZTF object ID   | `ZTF21aaxtctv`                                                                                                             |
| TNS name        | `SN 2021hpr`                                                                                                               |
| Fink URL        | https://fink-portal.org/ZTF21aaxtctv                                                                                       |
| Fink class      | SN Ia (Early SN Ia module flagged anomalous blue excess)                                                                   |
| LC endpoint     | `POST https://fink-portal.org/api/v1/objects` body: `{"objectId":"ZTF21aaxtctv","output-format":"json"}`                   |
| Cutout endpoint | `POST https://fink-portal.org/api/v1/cutouts` body: `{"objectId":"ZTF21aaxtctv","kind":"Science","output-format":"array"}` |

---

## Packet 07 — JADES 9186 (Little Red Dot) [TRIAGE | JWST]

| Field                 | Value                                                                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Survey ID             | `JADES 9186`                                                                                                                    |
| Field                 | GOODS-S                                                                                                                         |
| RA, Dec (approx, deg) | 53.1228, −27.7921                                                                                                               |
| Redshift              | 4.99                                                                                                                            |
| JWST proposals        | GO #1180, #1210 (JADES)                                                                                                         |
| MAST HLSP catalog     | https://archive.stsci.edu/hlsp/jades                                                                                            |
| ESA image reference   | https://esawebb.org/images/littlereddots/                                                                                       |
| Key paper             | arXiv:2404.03576 (Kocevski et al. LRD census)                                                                                   |
| astroquery call       | `Observations.query_criteria(proposal_id=['1180','1210'], instrument_name='NIRCAM', s_ra=53.1228, s_dec=-27.7921, radius='5s')` |

---

## Packet 08 — Euclid Q1 Grade-B Lens (EUC J095930) [TRIAGE | Euclid Q1]

| Field         | Value                                 |
| ------------- | ------------------------------------- |
| Euclid ID     | `EUC J095930.93-023517.1`             |
| RA, Dec (deg) | 149.879, −2.588                       |
| Grade         | B (probable lens, unconfirmed)        |
| Q1 field      | EDF-S footprint                       |
| Paper         | arXiv:2503.15325 (Discovery Engine B) |
| Q1 catalog    | https://www.euclid-ec.org/science/q1/ |
| ESA SAS       | https://easidr.esac.esa.int/sas/      |

**Design note**: Grade B means morphological evidence for lensing but no
spectroscopic confirmation. Intentionally ambiguous for the triage test.

---

## Packet 09 — SN 2020jfo / ZTF20abgssah [CTRL | Lasair]

| Field         | Value                                                                          |
| ------------- | ------------------------------------------------------------------------------ |
| ZTF object ID | `ZTF20abgssah`                                                                 |
| TNS name      | `SN 2020jfo`                                                                   |
| Type          | SN IIP (spectroscopically confirmed)                                           |
| Host          | NGC 4303 (M61), z=0.00522                                                      |
| RA, Dec (deg) | 185.4791, +4.4737                                                              |
| Lasair URL    | https://lasair-ztf.lsst.ac.uk/objects/ZTF20abgssah/                            |
| Lasair API    | `GET https://lasair-ztf.lsst.ac.uk/api/v1/objects/ZTF20abgssah/`               |
| LC            | `GET https://lasair-ztf.lsst.ac.uk/api/v1/lightcurves/?objectIds=ZTF20abgssah` |
| Key paper     | arXiv:2105.11954                                                               |

**Expected agent behaviour**: CTRL — no exotic labels; low follow-up priority.

---

## Packet 10 — Subtraction Artefact ZTF19aadcmkv [CTRL | ALeRCE]

| Field             | Value                                                                     |
| ----------------- | ------------------------------------------------------------------------- |
| ZTF object ID     | `ZTF19aadcmkv`                                                            |
| ALeRCE URL        | https://alerce.science/object/ZTF19aadcmkv                                |
| Stamp class       | bogus                                                                     |
| Real-Bogus score  | < 0.4                                                                     |
| Artefact cause    | PSF subtraction dipole near saturated star                                |
| Probabilities API | `GET https://api.alerce.online/ztf/v1/objects/ZTF19aadcmkv/probabilities` |
| Stamps API        | `GET https://api.alerce.online/ztf/v1/objects/ZTF19aadcmkv/stamps`        |

**Expected agent behaviour**: CTRL — classify as artefact; do not follow up.

---

## Packet 11 — JWST NIRCam Wisp Artefact [CTRL | JWST]

| Field                 | Value                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------- |
| Artefact type         | NIRCam scattered-light "wisp"                                                                |
| Affected filters      | F150W, F200W                                                                                 |
| Reference field       | JADES GOODS-S, Module B                                                                      |
| RA, Dec (approx, deg) | 53.162, −27.790                                                                              |
| JWST proposal         | GO #1180                                                                                     |
| STScI documentation   | https://jwst-docs.stsci.edu/known-issues-with-jwst-data/nircam-known-issues                  |
| astroquery call       | `Observations.query_criteria(proposal_id='1180', instrument_name='NIRCAM', filters='F150W')` |

**Expected agent behaviour**: CTRL — identify wisp morphology; reject as non-astrophysical.
A trained vision agent should flag the extended, arc-like, non-point-source pattern.

---

## Packet 12 — CHIME RFI Event FRB 20181224E [CTRL | CHIME]

| Field                 | Value                                                          |
| --------------------- | -------------------------------------------------------------- |
| TNS name              | `FRB 20181224E`                                                |
| CHIME Catalog 1 field | `tns_name == 'FRB 20181224E'`                                  |
| excluded_flag         | True                                                           |
| Probable cause        | RFI / instrumental artefact                                    |
| Catalog CSV           | https://www.chime-frb-open-data.github.io/catalog/catalog1.csv |
| Python filter         | `df[df['tns_name']=='FRB 20181224E']['excluded_flag']` → True  |

**Expected agent behaviour**: CTRL — `excluded_flag=True` should propagate
to a `reject` label; no astrophysical interpretation.

---

## API authentication notes

| Service           | Auth requirement                                            |
| ----------------- | ----------------------------------------------------------- |
| ALeRCE            | None for public read endpoints                              |
| Fink Portal       | None for public API                                         |
| Lasair            | Free account token in `Authorization: Token <token>` header |
| MAST (astroquery) | None for public data; token needed for proprietary          |
| TNS               | API key needed for bulk queries; free registration          |
| Euclid SAS        | ESA account; rolling public access                          |
| CHIME open data   | None for catalog CSV; baseband data requires registration   |

---

```python
from astroquery.simbad import Simbad
from astropy.coordinates import SkyCoord
import astropy.units as u

coord = SkyCoord(ra=RA_DEG, dec=DEC_DEG, unit='deg', frame='icrs')
result = Simbad.query_region(coord, radius=5*u.arcsec)
```

Fetch all 12 packets:

python fetch_observation_packets.py --all --out-dir ./packets

The multi-agent system reads from ./packets/

# e.g. python langgraph_pipeline.py --packets-dir ./packets
