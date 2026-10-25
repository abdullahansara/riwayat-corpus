# Hadith master database - build report

- hadith: **924,787**  |  chain mentions: **5,677,620**  |  canonical narrators: **193,014** (105,955 appear in at least one chain)  |  narrator name forms: **708,824**
- hadith with inline-tagged text (narrator ids embedded): 911,709
- mentions with a narrator id: 4,873,059 (85.8%); without: 804,561
- mentions whose character span was located in the text: 5,660,818 (99.7%); span range errors: 0

## Chain tiers (by tradition)
- **A** chain confirmed by two independent annotations (hadith-kg and Sanadset agree)
- **B** one curated annotation (hadith-kg, Sanadset tags, or Thaqalayn hyperlinks)
- **C** produced by our parser / our parse of Sanadset (lower confidence)
- **none** no chain found in the text

| tradition | tier | hadith |
|---|---|---|
| shia | B | 25,155 |
| shia | C | 12,152 |
| sunni | A | 304,601 |
| sunni | B | 366,611 |
| sunni | C | 203,242 |
| sunni | none | 13,026 |

## How narrator ids were assigned (mentions)

| method | mentions | mean confidence |
|---|---|---|
| source_annotation_kg | 3,001,624 | 0.94 |
| linker_context | 508,841 | 0.95 |
| candidates_only | 340,498 | 0.00 |
| linker_unique | 313,261 | 1.00 |
| ranker | 280,215 | 0.94 |
| surgery_asserted | 164,635 | 0.95 |
| source_annotation_thaqalayn | 100,843 | 0.90 |
| gap_model_unresolved | 96,499 | 0.00 |
| new_narrator_from_full_name | 90,081 | 0.60 |
| gap_model_candidates | 69,638 | 0.00 |
| ranker2 | 69,035 | 0.99 |
| name_lookup_unique_v2 | 67,146 | 0.85 |
| joint_unresolved | 65,522 | 0.00 |
| unresolved | 58,809 | 0.00 |
| name_lookup_unique | 54,906 | 0.85 |
| gap_model_unique | 41,724 | 0.80 |
| thaqalayn_id_on_reparsed_span | 33,771 | 0.70 |
| linker_relative_unresolved | 31,605 | 0.00 |
| name_plus_graph_edges | 26,923 | 0.75 |
| linker_unique+backoff | 24,635 | 1.00 |
| joint_candidates | 23,706 | 0.00 |
| relative_unresolved | 19,480 | 0.00 |
| linker_unmatched | 18,968 | 0.00 |
| gap_filled_unresolved | 18,878 | 0.00 |
| joint_unique | 17,083 | 0.80 |
| matn_chain_extracted | 15,407 | 0.95 |
| linker_relative_father | 13,525 | 0.90 |
| linker_alias_patch | 13,019 | 0.82 |
| joint_relative_unresolved | 12,616 | 0.00 |
| linker_anonymous | 10,330 | 0.00 |
| gap_filled_candidates | 9,359 | 0.00 |
| linker_context+backoff | 8,926 | 0.81 |
| surgery_relative_father | 6,445 | 0.84 |
| sandwich | 6,352 | 0.92 |
| gap_filled_unique | 5,507 | 0.80 |
| demoted:linker_context | 4,762 | 0.00 |
| claude_label | 4,387 | 0.95 |
| demoted:linker_unique | 3,287 | 0.00 |
| claude_reparse_unresolved | 3,187 | 0.00 |
| demoted:name_lookup_unique_v2 | 2,672 | 0.00 |
| demoted:name_plus_graph_edges | 2,320 | 0.00 |
| linker_prior_only | 2,196 | 0.39 |
| gap_relative_unresolved | 2,104 | 0.00 |
| fix_55_merge_conflict | 2,048 | 0.00 |
| surgery_tafsir_ibn_zayd | 2,023 | 0.95 |
| relative_father_edges | 1,695 | 0.80 |
| demoted:linker_context+backoff | 1,287 | 0.00 |
| demoted:linker_unique+backoff | 1,284 | 0.00 |
| claude_chain_unresolved | 969 | 0.00 |
| linker_unmatched_weak_dropped | 844 | 0.00 |
| fix_47_connector | 760 | 0.00 |
| manual_gold | 384 | 1.00 |
| claude_missed_candidates | 348 | 0.00 |
| claude_chain_candidates | 335 | 0.00 |
| claude_chain_unique | 205 | 0.80 |
| claude_missed_unique | 196 | 0.80 |
| claude_missed_unresolved | 158 | 0.00 |
| demoted:linker_alias_patch | 126 | 0.00 |
| manual_gold_unverified_id | 114 | 0.87 |
| fix_62_conflict_wrong | 49 | 0.00 |
| linker_prior_only+backoff | 44 | 0.37 |
| fix_62_relation_reassigned | 20 | 0.90 |
| fix_62_relation_wrong | 4 | 0.00 |

## Parser scores on data never used in training
```

```

## Reference chains kept separately (full multi-isnad, not merged into hadith)
mids: 13,404, semantichadith: 34,457

## Sample records

**Tier A** H0008055 (sunni, صحيح مسلم #1024)

وحَدَّثَنِي <N id="N0000323">زُهَيْرُ بْنُ حَرْبٍ</N> ، <N id="N0000903">وَابْنُ أَبِي عُمَرَ</N> ، قَالَ <N id="N0000323">زُهَيْرٌ</N> : حَدَّثَنَا <N id="N0000384">سُفْيَانُ بْنُ عُيَيْنَةَ</N> ، عَنِ <N id="N0000560">ابْنِ أَبِي لَبِيدٍ</N> ، عَنْ <N id="N0000602">أَبِي سَلَمَةَ</N> ، عَنِ <N id="N0000609">عَبْدِ اللَّهِ بْنِ عُمَرَ</N> ، قَالَ : سَمِعْتُ رَسُولَ اللَّهِ ﷺ ، يَقُولُ : لَا تَغْلِبَنَّكُمْ الأَعْرَابُ عَلَى اسْمِ صَلَاتِكُمْ ، أَلَا إِنَّهَا الْعِشَاءُ ، وَهُمْ يُعْتِمُونَ بِالإِبِلِ

**Tier B** H0910078 (shia, man-la-yahduruhu-al-faqih #man-la-yahduruhu-al-faqih:3:3:44:5)

٤٥٨٧ - وَ<N id="N0153109">رُوِيَ</N> عَنْ <N id="N0152841">مُحَمَّدِ بْنِ إِسْمَاعِيلَ بْنِ بَزِيعٍ</N> قَالَ سَأَلَ رَجُلٌ اَلرِّضَا عَلَيْهِ اَلسَّلاَمُ :
عَنِ اَلرَّجُلِ يَتَزَوَّجُ اِمْرَأَةً مُتْعَةً وَ يَشْتَرِطُ عَلَيْهَا أَنْ لاَ يَطْلُبَ وَلَدَهَا فَتَأْتِي بَعْدَ ذَلِكَ بِوَلَدٍ فَيُنْكِرُ اَلْوَلَدَ فَشَدَّدَ فِي ذَلِكَ وَ قَالَ "يَجْحَدُ وَ كَيْفَ يَجْحَدُ" إِعْظَاماً لِذَلِكَ قَالَ اَلرَّجُلُ فَإِنِ اِتَّهَمَهَا، قَالَ "لاَ يَنْبَغِي لَكَ أَنْ تَتَزَوَّجَ إِلاَّ بِمَأْمُونَةٍ إِنَّ اَللَّهَ عَزَّ وَ جَلَّ قَالَ:
۝ اَلزّٰانِي لاٰ يَنْكِحُ إِلاّٰ زٰانِيَةً أَوْ مُشْرِكَةً وَ اَلزّٰانِيَةُ لاٰ يَنْكِحُهٰا إِلاّٰ زٰانٍ أَوْ مُشْرِكٌ وَ حُرِّمَ ذٰلِكَ عَلَى اَلْمُؤْمِنِينَ ۝

**Tier C** H0695149 (sunni, المجالسة وجواهر العلم للدينوري #2153)

2078 حَدَّثَنَا <N>أَحْمَدُ</N> ، نَا <N guess="N0002744">مُحَمَّدُ بْنُ عَبْدِ الْعَزِيزِ</N> ، نَا <N guess="N0006008">ابْنُ عَائِشَةَ</N> ، قَالَ : سَمِعْتُ <N>أَبِي</N> يَقُولُ : " كَانَ دَعْوَةُ أَبِي بَكْرِ بْنِ عَبْدِ اللَّهِ الْمُزَنِيِّ لِإِخْوَانهِ : زَهَّدَنَا اللَّهُ وَإِيَّاكُمْ زُهْدَ مَنْ أَمْكَنَهُ الْحَرَامُ وَالذُّنُوبُ فِي الْخَلَوَاتِ ، فَعَلِمَ أَنَّ اللَّهَ يَرَاهُ فَتَرَكَهُ .

## Tables
`hadith`, `chain_mention` (one row per narrator with span, id, method, confidence, source reference, alternatives), `narrator` (our id, standard name, attributes), `narrator_name` (every name form with type, source and observed count), `narrator_source_id` (our id <-> each source id), `narrator_edge` (teacher->student counts from the chains), `narrator_edge_seed` (teacher/student links from Itqan/AR-Sanad), `reference_chain` (MIDS Sahih Muslim and SemanticHadith full isnads).

## Known limits
- Whole-chain exactness of the parser is 69-81% on held-out data (narrator-level F1 0.94-0.97); tiers say how much to trust each chain.
- hadith-kg and SemanticHadith share an upstream annotation, so their agreement is not fully independent; MIDS (Sahih Muslim) was the independent check.
- Rare narrators may still be duplicated across sources where co-occurrence or exact-name evidence was insufficient.
- Shi'i narrator ids from Thaqalayn are kept separate from Sunni ids (no cross-tradition merging).
