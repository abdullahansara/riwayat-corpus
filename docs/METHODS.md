# Methods
Run from the repository root with `HADITH_ROOT` set (default `./data`); raw sources go in `$HADITH_ROOT/sources/<Name>/`, output goes to `$HADITH_ROOT/HadithMaster/`.
Scripts import `paths.py`; run them as `python pipeline/<script>.py` (not with `-I`).

1. `parse_thaqalayn.py` parse the Thaqalayn Shi'i corpus to `thaqalayn_hadith.jsonl`.
2. `train6.py` train the CRF chain parser (final model `parser_v9`; uses `sanad_crf.py`, `llm_labels.py`, `train_labels.tsv`, `eval_labels.tsv`).
3. `build_narrators.py` build the narrator inventory by union-find over crosswalks (hadith-kg, Itqan / AR-Sanad, SemanticHadith, MIDS, Thaqalayn).
4. `assemble_master.py parser_v9` assemble hadith, chains, tiers and mentions into `hadith_master.db`.
5. `resolve_unresolved.py` second-pass resolver (name variants plus teacher/student graph).
6. `create_new_narrators.py` create narrators from unmatched full names.
7. `fix_muslim_ids.py` and `merge_prefix.py` merge duplicate IDs using co-occurrence on MIDS-aligned Sahih Muslim hadith; audited in `narrator_merge`. Both print precision/recall against MIDS.
8. `postprocess.py` rebuild edges, observed names, narrators.csv and the quality report (idempotent).
9. `flag_suspect_narrators.py` add `narrator_flag` and the flags column.

10. In-place surgery (the raw sources were later deleted, so these run on the database itself; each logs to `surgery_log`):
    `fix_01_cleanup` (junk and over-long name forms), `fix_02_disambiguate` / `fix_02b_assert` (ID chooser; asserts an ID only above a margin threshold by name length, otherwise stores a weak guess), `fix_03_biography` (biography/rijal entries), `fix_04_split_merged` / `fix_04b_repair_split_ids` (merged mentions split, IDs repaired), `fix_05_relatives` (أبيه / جده resolved through the preceding narrator), `fix_06_recover_spans`, `fix_07_matn_boundary`, `fix_08_merge_duplicates` (identical normalised names with compatible dates and disjoint sources; 1,802 merges), `fix_09_purge_observed_forms`, `fix_10_matn_sanad` (isnad found inside a matn moved into the chain), `fix_11_matn_clean` (+`fix_11c`): matn = everything after the last narrator and its connectors; commentary and glued second isnads cut, `fix_12_clean_std_names`, `fix_16_validate_ids` (observed name forms and IDs that contradict their own surface text removed/demoted; hub narrator N0000600 had absorbed unrelated name forms), `fix_17_fill_gaps` (narrators missed by the parser, found right after a transmission verb), `fix_13_regenerate` (text_tagged, narrator_edge, counts), `fix_14_export` (narrators.csv, samples), `fix_15_report` (QUALITY_REPORT.md).
    Finally `tools/gold_to_db.py --apply` writes the 100 hand-verified gold chains.

`pipeline/archive/` holds the exploratory scripts of the earlier stages (Sanadset-to-hadith-kg alignment and linking, `hadith_unified.csv`, etc.),
whose outputs `assemble_master.py` reads from `sources/Sanadset/`. They are kept for provenance and are not runnable as-is
(paths replaced by `<ROOT>` / `<WORKDIR>`); the rebuild is therefore not fully reproducible from the raw sources alone.

## Phase 2 (Claude labels + trained models), Oct 2026
Rules had reached diminishing returns, so the judgement-heavy steps were done by **Claude agents labelling samples, models generalising, and Claude adjudicating the leftovers**.
All agent output is kept in `labels/*_out/` and, for the hadith-level labels, in the tables `claude_label_hadith` / `claude_label_mention` (fix_38).
- `fix_19` samplers build label chunks; labellers return matn start/end phrases, mention kinds (narrator / relative / anonymous / not_a_narrator), chosen narrator IDs and missed names.
- `fix_21/22` matn boundary models (logistic regression on candidate boundaries); `fix_23/24` missed-transmitter tagger; `fix_25/26` narrator-ID ranker (gradient boosting, asserted at P>=0.85);
  `fix_29/30` same-person pair model and duplicate-narrator merge; `fix_27` classification of chainless texts; `fix_31/32` Claude matn boundaries and re-parse of the 457 unparsed Shi'i chains.
- `fix_33/34/35/36` joint BiGRU tagger (models/joint*.pt): one pass gives transmitter spans, matn start and matn end; applied at confidence >= 0.9 (matn) and span probability >= 0.9 (new names).
- `fix_37` narrated-opening classifier: moves the matn start before a narrated opening (سألت ... / خرجنا ...) that was left in the chain.
- `fix_38` Claude narrator choices written to mentions (id_method claude_label); label tables.
- `fix_39` isnad-map nodes for relatives and anonymous transmitters (see SCHEMA).
- `fix_41/42/43` chain-parse risk model (models/chain_risk.pkl), Claude re-parse of risky chains under one written definition of a transmitter, and clean-up of leftover rows.
- Evaluation: `tools/gold_score.py` (100 gold chains), `pipeline/fix_40_chain_eval.py` (hadith-level chain match against Claude labels), blind audits by independent agents (labels/audit*_out).
Definition of a transmitter used by the re-parse: every person named as a link in the narration chain (relatives, kunya-only and anonymous links included), each introduced by a connector; not the Prophet, not the book author announcing,
not persons that appear only inside the narrated story; a ح transfer starts a new branch.
