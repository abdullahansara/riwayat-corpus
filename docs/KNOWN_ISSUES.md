# Known issues and caveats
- **Tier C chains (214,939 hadith)** come from our CRF parser alone. Whole-chain exact match is 68–88 % on held-out sets; errors are mostly chain/matn boundary calls and unusual phrasing.
- **Matn** (`text[matn_start:matn_end]`) was re-derived for ≈446K hadith (everything after the last narrator and connectors; commentary and glued isnads cut). A blind read of 45 matns across tiers found them clean, but about 1–3 % (estimate, not measured on a large sample) still carry isnad or commentary: mostly biography/rijal entries (tier C) and chain links that were never tagged as narrators. ≈4K tier B and ≈4.3K tier C hadith still start inside the chain, 1,102 tier C have no `matn_start`; originals are in `matn_start_source` / `matn_end_source`.
- **IDs:** 4,473,775 mentions (85.7%) have an asserted ID; 559,763 (10.7%) only a weak `guess_narrator_id` (`candidates_only`, ≈30 % right on the gold set before fix_16 removed contradicting guesses; treat as noise-prone); 184,835 (3.5%) none. `fix_16` demoted 23,063 asserted IDs that contradicted their own surface text (`id_method` starts with `demoted:`). On the 100-chain gold set the pre-surgery asserted-ID accuracy was 79.8 %.
- **Gap-filled mentions:** `fix_17` added 66,047 narrators the parser had skipped (flag `gap_filled`; ≈90 % correct on a hand-read sample; most carry no ID because the name is ambiguous).
- **Unlocated mentions:** 17,299 tier B mentions come from the source annotation but their name could not be found in the text (`flags = span_not_located`, no span). 457 tier C Shi'i hadith have a chain but no parsed mentions (`chain_unparsed`).
- **Created narrators:** ≈50K narrators were created from unmatched full names (`id_method = new_narrator_from_full_name`, confidence 0.6). Some may duplicate existing narrators.
- **Narrator flags** (`narrator_flag` table, `flags` column of narrators.csv):
  `merged_names_suspect` (1,822): created by us and the name contains "عن" or "،", so the parser probably failed to split two narrators;
  `compound_source_name` (8,468): rijal-source names of the form "X ، عن Y";
  `overlong_name` (2,792): standard name over 120 characters, usually a full genealogy.
- **Duplicates:** the same person can still exist under two IDs. 214 merges were evidenced on Sahih Muslim (MIDS) and 1,802 by `fix_08` (identical normalised name, compatible death years, disjoint sources, name not shared by >3 records); all are in `narrator_merge`. Common names (e.g. عبد الرحمن بن عبد الله) with many records are deliberately left unmerged: 11K name groups still hold ≥2 records, many of them genuinely different people.
- **Narrator names:** 13,125 corrupt `std_name` values (rijal codes, page numbers, biography text) were cut back to the name (original in `surgery_log`); 333 records with no usable name are flagged `junk_name`; ≈97K narrator records have no mention in any chain.
- **Edges:** `narrator_edge.suspect` marks 28K edges where the teacher died ≥30 years after the student and 27K in 2-cycles; they are flagged, not removed. Edges were not rebuilt after the 100 gold chains were written.
- **Duplicate texts:** 954 hadith (466 texts) share identical text (`duplicate_text`).
- **Shi'i narrators** have separate IDs from Sunni narrators even when the same person.
- **Shared upstream:** hadith-kg and SemanticHadith share one upstream annotation; their agreement is not independent evidence. MIDS is the independent check.
- **Referential isnads** ("بهذا الإسناد", "بمثله"): MIDS expands them into full chains, we keep only the chain as written.
- **Arabic text** is taken from the sources; it has not been collated against OpenITI.
- `reference_chain.hadith_id` is filled for 6,281 MIDS rows only.

## Status after Phase 2 (Oct 2026) - measured, not promised
- Transmitter lists: against Claude labels on 1,458 held-out hadith, 77% of database chains match exactly (88% when a missing/extra name at the very end that is not introduced by a connector is tolerated); the joint tagger alone 79% / 83%.
  Two independent Claude labellers agree with each other on about 97%. Blind audits of 200 random hadith: chain complete 84.5%, matn start 88.5%, matn end 96%, assigned-ID precision 95%.
- About 1.4K of the riskiest chains were re-parsed by Claude agents (fix_42): a 100-hadith audit found 78% chain-complete and 41% start-correct. The failures are multi-route hadith whose report sits between routes or whose later routes end in stubs.
  Stub/reference matns ("مثله", "بنحوه") number about 1,000 hadith (0.1%).
- The chain-risk model (models/chain_risk.pkl, labels/chain_risk.db) ranks every hadith; hadith with risk >= 0.05 (about 313K) have not been re-parsed. A run of 40,000 was started and stopped after 41 chunks to save tokens.
- Narrator identity: 84.6% of mentions have a firm ID; about 505K have only a weak guess and agents rejected more than half of the weak guesses they were shown; treat weak guesses as leads. About 785K named mentions have no map node yet.
- The registry has wrong dates and junk duplicate records (agents found examples). The chronology check (tools/chronology_check.py) flags 2.2% of adjacent firm-ID pairs whose death years are out of order, mostly from source annotations.
- Relatives (أبيه ...) and anonymous transmitters are deliberately kept unidentified; they have map nodes with floruit ranges.

## Status after Phase 3 (Oct 2026)
**Measured**
- Gold set: 100 hand-verified chains (468 verified narrators): chain exact 100%, narrator F1 1.000. It is small and was used to tune rules, so it is a regression test, not an estimate of corpus accuracy.
- Chains re-parsed by agents (the riskiest 1,158): independent audit of 60: chain complete 95%, matn start 90%, better than the stored version in every audited case.
- Newly assigned narrator IDs (about 138K, `id_method` `ranker2` / `sandwich`): independent reviewer samples give roughly 95-97% precision after the final rules; the rules were fitted on those samples, so treat this as optimistic.
**Limitations**
- **No independent authority for narrator identity.** About 62% of asserted IDs come from one source annotation and were not independently verified beyond the gold set and small samples. Only 18% of narrators have a death year.
- **Wrong merges and duplicate records remain.** Homonym confusions are visible in parallel chains (Sufyan b. Said / b. Uyayna; Hammad b. Zayd / b. Salama; Sulayman al-Ahwal / al-A'mash), and many mentions sit on duplicate records of one person (Layth b. Sa'd / al-Layth b. Sa'd). A merge audit repaired the worst targets, milder ones were not touched.
- **Unresolved mentions:** 757,514 (13.3%) carry no ID, by design for relatives, anonymous links and ambiguous bare names (about 127K of these sit on `isnad_node` records); 47,047 carry only a weak guess.
- **Boundaries outside the audited set** are as good as the original parser (tier C: 68-88% exact chain match). Spot checks still find matn starts that fall mid-phrase and occasional wrong narrators. The corpus-wide error rate has not been measured.
- **Parallel versions:** about 56% of hadith have a parallel version; chains of parallels sometimes differ in an extra or missing link, which may be a parsing error. Not systematically reviewed.
- **Same narrator twice in one chain:** 67,341 hadith; many are genuine multi-route chains, some are errors.
- **`narrator_edge` (475,989)** was built from our own chains before the Phase 3 ID changes and was not rebuilt; it is not independent evidence.
- **Small known defects:** 57 hadith with a chain tier but no mentions, 52 without `text_tagged`, 121 narrators with an empty standard name, 16,802 unlocated mentions, 1,081 extra copies of identical text (flagged in `dup_group`, not removed).
- Shi'i narrators still have separate IDs from Sunni narrators even when they are the same person.
