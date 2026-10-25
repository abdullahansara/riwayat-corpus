# Schema (SQLite)
- `hadith(id, tradition, book, number, source_ids, text, text_tagged, matn_start, matn_end, chain_source, chain_tier, n_narrators, flags, matn_start_source, matn_end_source)` — `text_tagged` has inline `<N id="N0000123">surface</N>`, `<N guess="…">` for weak IDs, `<N>` for none. The matn is `text[matn_start:matn_end]`; `matn_*_source` hold the boundaries before surgery. Flags include `matn_start_extended`, `matn_commentary_cut`, `matn_isnad_cut`, `matn_leading_link_cut`, `matn_start_kept`, `matn_has_mentions`, `matn_isnad_only`, `duplicate_text`, `chain_unparsed`, `gold_reviewed`.
- `chain_mention(hadith_id, pos, start, end, surface, narrator_id, id_method, id_confidence, id_source_ref, alternatives, flags, chain_no, guess_narrator_id, guess_confidence)` — `chain_no` 1 = main chain, 2+ = supplementary chains in the same text; `narrator_id` is NULL when the ID was not asserted, and then `guess_narrator_id` may hold the best weak candidate. Mentions with `flags` = `span_not_located` (≈17K, tier B) come from the source annotation and could not be found in the text (start/end/surface NULL).
- `narrator(id, std_name, std_name_source, tradition, death_year, birth_year, tabaqa, city, ..., n_sources)`
- `narrator_name(narrator_id, form, norm, type, source, observed_count)` — all alternative names
- `narrator_source_id(narrator_id, source, source_id, name)` — crosswalk to source datasets
- `narrator_edge(student, teacher, n_hadith, n_tier_a, suspect)` (`suspect`: teacher_died_30y_after_student, two_cycle), `narrator_edge_seed`
- `reference_chain(source, unit, sanad_no, narrator_ids, hadith_id)` — MIDS / SemanticHadith full isnads (hadith_id filled for 6,281 MIDS rows)
- `narrator_merge(old_id, new_id, reason, jaccard, n_hadith)` — audit of duplicate merges
- `narrator_flag(narrator_id, flag)` — quality flags: merged_names_suspect, compound_source_name, overlong_name (see KNOWN_ISSUES)
- `surgery_log(step, kind, key, old, new)` — every in-place change made by pipeline/fix_01…fix_14 (old value kept), so changes are reversible
- `removed_mention`, `purged_name_form` — mentions and name forms deleted by surgery (kept for audit)
- `gold_replaced_mention` — the original mentions of the 100 gold hadith before the hand-verified chains replaced them
- `narrator_flag` also contains `junk_name` (333 records whose name was only codes/garbage)

## Added in Phase 2
- `claude_label_hadith(hadith_id, source, chain_status, matn_start_phrase, matn_end_phrase, note)` and `claude_label_mention(hadith_id, start, surface, kind, choice, source)`: the Claude labels (7,290 hadith, 38,265 mentions).
- `chain_mention.id_method` new values: `claude_label`, `ranker`, `joint_unique`, `joint_candidates`, `gap_model_unique`, `claude_missed_*`, `claude_chain_*`, `claude_reparse_unresolved`.
- `chain_mention.node_key` and table `isnad_node(node_key, kind, label, relation, base_key, fl_from, fl_to, fl_basis, n_mentions, n_hadith)`; view `mention_node(mention_rowid, hadith_id, chain_no, pos, node)`.
  Relatives and anonymous transmitters keep their unknown identity but get a map node: `rel:<relation>:<base narrator or collector>` and `anon:<class>:<student>:<teacher>`;
  `fl_from/fl_to` = probable floruit (AH) from the death years of the nearest identified teacher and student in the chain (a one-sided range is set 40 years wide). The catch-all record N0003708 is never a node.
- `narrator_merge` now holds 14,643 merges (fix_08 and fix_30). `surgery_log` steps fix_19 to fix_43 record every change (old values are stored).
- Flags on hadith: `model_start`, `model_end`, `joint_start`, `joint_end`, `frame_start`, `claude_matn`, `claude_parsed`, `claude_reparsed`, `joint_names`, `gap_model`, `no_sanad_in_source`, `fragment`, `referential_opening`.
