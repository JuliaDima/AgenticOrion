# Agentic Orion

**Multi-agent astronomical triage for next-generation survey streams.**

---

## 🔭 Live Dashboard

> ### [juliadima.github.io/AgenticOrion](https://juliadima.github.io/AgenticOrion/)

Browse every run, inspect agent traces, view light curves, and explore benchmark results — no local setup required.

---

## What It Does

Agentic Orion receives compact observation packets from telescopes and brokers — Rubin/ZTF alerts, JWST cutouts, CHIME FRB catalogs, Euclid lensing candidates — and routes each one through a LangGraph multi-agent pipeline that produces a structured, auditable triage report within ~50 seconds.

```
Supervisor
    └── Observation Characterizer
            ├── Astrophysical Interpreter  ─┐
            ├── Artefact Checker            │  parallel fan-out
            ├── Novelty Assessor            │
            └── Context Retriever          ─┘
                        └── Evidence Aggregator
                                └── Follow-up Prioritizer
                                        ├── Code Executor  (optional)
                                        └── Synthesis / Report
```

Each agent is a specialist: the characterizer extracts observables, four branches run simultaneously to assess astrophysics, artefacts, novelty, and literature context, and the aggregator debates them before issuing a triage verdict (`HIGH_PRIORITY`, `MEDIUM_PRIORITY`, `REJECT_ARTEFACT`, `REJECT_CONTROL`).

---

## Why Multi-Agent?

| | Multi-agent (Orion) | Serial single-agent |
|---|---|---|
| **Parallelism** | 4 branches in parallel | sequential |
| **Wall time** | ~49 s / object | ~65 s / object |
| **Speedup** | **1.33×** | baseline |
| **Characterization score** | **0.78** | 0.27 |
| **Objects / night** (100 workers) | **~72 000** | ~55 000 |

A human astronomer reviewing 20 min/object covers ~24 objects per 8-hour shift. At 100 parallel cloud workers, Agentic Orion covers **72 000** — a **3 000× throughput advantage** — while delivering a multi-wavelength, structured, citable report every time.

At 600 workers, the full Rubin LSST priority-tier alert stream (~500 k objects/night) is covered within the same 10-hour observing window.

---

## Observation Packets

12 curated packets span the breadth of next-generation survey science:

| # | Object | Mission | Type |
|---|--------|---------|------|
| 01 | AT2018cow | ZTF / ALeRCE | RETRO — fast blue transient |
| 02 | FRB 20121102A | CHIME | RETRO — repeating FRB |
| 03 | Maisie's Galaxy | JWST / NIRCam | RETRO — z ≈ 11.4 galaxy |
| 04 | EUCL J081705 | Euclid / VIS+NISP | RETRO — strong lens |
| 05 | AT2020ixi | ZTF / ALeRCE | TRIAGE — SN with CSM bump |
| 06 | SN 2021hpr | ZTF / Fink | TRIAGE — peculiar SN Ia |
| 07 | JADES 9186 | JWST / NIRCam+NIRSpec | TRIAGE — AGN or starburst at z ≈ 5 |
| 08 | EUC J095930 | Euclid / VIS+NISP | TRIAGE — unconfirmed lens |
| 09 | SN 2020jfo | ZTF / ALeRCE | CTRL — ordinary SN IIP |
| 10 | — | ZTF / ALeRCE | CTRL — imaging artefact |
| 11 | JWST wisp | JWST / NIRCam | CTRL — scattered-light artefact |
| 12 | FRB 20181224E | CHIME | CTRL — RFI / excluded burst |

A set of **BLIND** variants (anonymised packets with identifying metadata removed) allows testing whether the system reaches the same triage verdict without knowing the ground-truth classification in advance.

---

## Repository Layout

```
research_workflow/
├── main.py                  # entry point — run a packet
├── graph.py                 # LangGraph graph construction
├── state.py                 # shared ResearchState TypedDict
├── agents/
│   ├── supervisor.py
│   ├── observation_characterizer.py
│   ├── astrophysical_interpreter.py
│   ├── artefact_checker.py
│   ├── novelty_assessor.py
│   ├── context_retriever.py
│   ├── evidence_aggregator.py
│   ├── followup_prioritizer.py
│   ├── code_executor.py
│   └── synthesis.py
├── tools.py                 # execute_python, extract_tokens
├── logging_db.py            # SQLite trace store
├── benchmark.py             # multi-agent vs single-agent evaluation
├── web/                     # static dashboard (GitHub Pages)
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── web_server.py            # local dev API server
packets/
└── packet_NN_<name>/
    ├── packet.json
    └── data/                # lightcurve CSV, alert JSON, FITS cutouts
```

---

## Running Locally

**Requirements:** Python 3.11+, an OpenAI API key.

```bash
pip install -r research_workflow/requirements.txt
export OPENAI_API_KEY=sk-...
```

**Run a packet:**

```bash
python research_workflow/main.py --packet 1        # AT2018cow
python research_workflow/main.py --packet 5        # AT2020ixi (triage)
python research_workflow/main.py --packet 12       # FRB 20181224E
```

**Local dashboard** (live API server):

```bash
python research_workflow/web_server.py
# → open http://localhost:8000
```

**Re-run benchmark:**

```bash
python research_workflow/benchmark.py
```

---

## Built With

- [LangGraph](https://github.com/langchain-ai/langgraph) — stateful multi-agent orchestration
- [LangChain / OpenAI](https://github.com/langchain-ai/langchain) — LLM calls (`gpt-4o-mini`)
- [ALeRCE](https://alerce.science/) / [Fink](https://fink-portal.org/) — ZTF alert broker data
- [CHIME/FRB Catalog 1](https://www.chime-frb.ca/) — fast radio burst data
- [JWST / Euclid public releases](https://esawebb.org/) — high-z and lensing data
