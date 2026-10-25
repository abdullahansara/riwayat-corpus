# Riwāyāt: A Corpus of Sunni and Shīʿī Hadith Transmission

A unified corpus of Sunni and Shīʿī hadith with parsed isnāds, matn boundaries and a narrator registry. (Working name of the build: HadithMaster; the database file is still called `hadith_master.db`.)

| | |
|---|---|
| Hadith | 924,787 (≈887K Sunni, ≈37K Shi'i), all with Arabic text |
| Chain mentions | 5,677,620 (5,368,184 main chain + 309,436 supplementary chains), 99.7% with a character span; 4,873,059 (85.8%) carry an asserted narrator ID, 47,047 (0.8%) only a weak `guess_narrator_id`, 757,514 (13.3%) none (incl. ≈127K relatives/anonymous links that sit on isnad nodes) |
| Narrators | 193,014 unique IDs (14,643 merged away), 708,824 name forms; only 105,955 appear in a chain, 18% have a death year |
| Student→teacher edges | 475,989 (adjacent mentions of one chain, built before the Oct 2026 ID changes; not rebuilt; derived from our own chains, so not independent evidence) |
| Reference isnads | 47,861 (MIDS Sahih Muslim, SemanticHadith) for independent comparison |

Every hadith carries `text_tagged`, the text with narrators marked inline: `<N id="N0000123">surface</N>` (asserted ID), `<N guess="N0000123">` (weak ID) or `<N>` (no ID).
The matn is `text[matn_start:matn_end]`; the text itself is never altered, and the original boundaries stay in `matn_start_source` / `matn_end_source`.
Every mention records *how* its ID was assigned (`id_method`) and how confident we are (`id_confidence`).
Narrator grading (thiqa etc.) is deliberately not included.

## Get the data
The 3.8 GB SQLite file is **not in this repository**. Download `hadith_master.db` from the release / data deposit
(link to be added) into `data/HadithMaster/`, then:

```
pip install -r requirements.txt
python tools/verify_db.py          # integrity check and counts
python examples/queries.py         # name lookup, a chain, a narrator's teachers
```

## Quality (see `docs/QUALITY_REPORT.md` and `docs/KNOWN_ISSUES.md`)
`hadith.chain_tier` says how far to trust each chain:

| Tier | Meaning | Hadith |
|---|---|---|
| A | hadith-kg and Sanadset annotations agree | 304,601 |
| B | one curated annotation | 391,766 |
| C | our CRF parser only | 215,394 |
| none | no chain (by design or fragment) | 13,026 |

Hand-verified gold set: 100 chains (`gold/`) are written into the database as `manual_gold`.
Parser on held-out data: chain exact-match 68–88 %, narrator F1 0.93–0.975.
Narrator IDs checked against MIDS on 2,948 Sahih Muslim hadith: precision 0.980, recall 0.973, 87.3 % identical narrator sets.
Weak IDs are kept apart from asserted ones (`guess_narrator_id`, `guess_confidence`); an ID is asserted only when its margin over the runner-up is large enough for the name length. Please read the known issues before relying on tier C or on narrators flagged in `narrator_flag`.

## Repository layout
```
docs/       SCHEMA, METHODS, SOURCES, KNOWN_ISSUES, QUALITY_REPORT
pipeline/   build scripts in run order (see docs/METHODS.md); archive/ = exploratory earlier stages, provenance only
tools/      verify_db.py
examples/   queries.py
sample/     small CSV samples of the main tables
data/       (git-ignored) place sources and the built database here; see data/README.md
```

## License
Our own contribution (code, parses, narrator identifications, labels, documentation) is dedicated to the public domain under CC0 1.0; no copyright is claimed. The hadith texts and source annotations come from third-party datasets
and remain subject to their licenses and citation requirements (e.g. hadith-kg is CC-BY-4.0); see `docs/SOURCES.md`. Please cite this work with `CITATION.cff` and credit the sources.

## Phase 2 summary (Oct 2026)
Claude agents labelled ~30K hadith/mentions; models trained on those labels (matn boundaries, missed transmitters, narrator-ID ranker, joint chain/matn tagger, duplicate merger, chain-risk model) were applied to the whole database
and audited blind by independent agents. See docs/METHODS.md, docs/QUALITY_REPORT.md and docs/KNOWN_ISSUES.md. Relatives and anonymous transmitters have isnad-map nodes (`isnad_node`, view `mention_node`).

## Phase 3 summary (Oct 2026)
After an independent audit the registry was cleaned (placeholders, standard names, merge integrity, weak guesses demoted to leads), narrator identification was extended with a reviewer-gated ranker and a parallel-text check, and the riskiest chains were re-parsed and re-bounded. Every change is logged and reversible; the 100-chain gold set still scores 100%.
**Please read the limitations in docs/KNOWN_ISSUES.md ("Status after Phase 3") before relying on the data statistically.**
