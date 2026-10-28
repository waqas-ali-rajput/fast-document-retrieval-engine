# Project management evidence (PLO-11)

> **Before submitting:**
> - Check that the dates (19–25 Oct 2026) and the review notes match what really happened.
> - Change the work split below wherever it differs from who actually did each part.
> - Each member rewrites their own contribution note (section 7) in their own words.
>
> The teacher will question each member about their part in the viva, so the split must be
> true.

**Team (batch 25CS):**

| Member | Roll no. | Role |
|---|---|---|
| **Waqas Ali** | 25CS061 | Team lead, integration and testing lead |
| **Mehran Ali** | 25CS009 | Indexing lead (hash table, inverted index, passage store) |
| **Gaffar** | 25CS067 | Ranking and top-k lead (heap, merge sort, rankers, scan baseline) |
| **Basit Azam** | 25CS113 | Corpus and evaluation lead (dataset, gold labels, preprocessing) |

Every module was reviewed by a member who did not write it (section 4).

## 1. How much work has each member done?

The work was split into four equal parts of about **25 % each**. Everyone also took part in
planning, the label cross-check, the report and the demo.

| Member | Code / files owned | Other deliverables | Tests owned | Report sections | Share |
|---|---|---|---|---|---|
| **Waqas Ali** (25CS061) | `main.cpp` (CLI, JSON output), `evaluation.cpp` (`rag eval`), `tests.cpp` (`rag test`), `gui/rag_gui.py` (desktop GUI), `build.bat`, `Makefile` | Integration of all modules, benchmarks, README, demo script, milestone tracking | T15, T19, all of `rag eval` | §6 Testing, §7.1 Method, Appendix A | 25 % |
| **Mehran Ali** (25CS009) | `hash_table.h` (separate chaining, FNV-1a, resize), `inverted_index.*` (postings, add/remove/update), `corpus.*` (passage store, id hash, duplicate detection) | Memory accounting, collision experiments | T05, T08, T09, T10, T11, T20, T21 | §3 Architecture, §7.4 Memory, §8 Complexity (index rows) | 25 % |
| **Gaffar** (25CS067) | `top_k_heap.h` (bounded heap), `merge_sort.h`, `retriever.*` (linear scan, indexed search, BM25 + freshness, coverage, evidence rule, tie-break) | Ranking investigation, heap vs sort timing | T06, T07, T12, T13, T13b, T14, T16, T22, T23 | §4 Ranking, §8 Complexity (search and top-k rows) | 25 % |
| **Basit Azam** (25CS113) | `text.*` (tokenizer, stop words, suffix rules, synonyms), `data/passages.txt` (31 documents, 155 passages incl. MUET CSE D24–D31), `data/queries.txt` (20 questions + gold labels), `data/synonyms.txt` | `data/DATASET.md`, label cross-check, Recall@3 analysis | T01, T02, T03, T04, T17, T18 | §1 Problem framing, §2 Inquiry, §5 Dataset, §7.2 Recall, §9 Limitations | 25 % |
| **All four** | — | Week-1 inquiry, design decisions (section 3), report §10 Reflection, rehearsal of the live demo | — | §10 | shared |

## 2. Dated milestone plan

Project period: **Monday 19 October – Sunday 25 October 2026**. The brief's Week 1 / 2 / 3
steps were done as three phases inside this period.

| Phase (brief week) | Dates | Milestone | Deliverables | Owner | Status |
|---|---|---|---|---|---|
| 1 (Week 1) | Mon 19 Oct – Tue 20 Oct 2026 | Inquiry and plan | Requirements list, definitions, learning questions, task breakdown, initial corpus (25 passages), 12+ questions, baseline design | All / Basit Azam | Done |
| 1 | Tue 20 Oct 2026 | Checkpoint 1 | One-page checkpoint record (section 3) | Waqas Ali | Done |
| 2 (Week 2) | Wed 21 Oct – Fri 23 Oct 2026 | Design and integration | Hash table, inverted index, linear scan, heap, rankers, one integrated CLI; full corpus; gold labels cross-checked | Mehran Ali, Gaffar, Basit Azam | Done |
| 2 | Fri 23 Oct 2026 | Checkpoint 2 | Scan vs index consistency check passes | Waqas Ali | Done |
| 3 (Week 3) | Sat 24 Oct – Sun 25 Oct 2026 | Verification and demo | Edge-case tests, benchmarks, ranking comparison, MUET CSE data, GUI, report, demo rehearsal | All | Done |
| 3 | [date set by the teacher] | Submission + live demo | Code, data, report, these records | All | Pending |

## 3. Week-1 checkpoint record (one page)

- **Problem as we understand it:** build the retrieval part of a RAG assistant. Return the
  top-k traceable passages, or "No supported evidence found". Compare a linear scan with an
  index.
- **Known:** arrays, linked lists, hashing basics, heaps and sorting from the course.
- **Unknown, to investigate (learning questions):**
  1. collision handling and resizing (Mehran Ali);
  2. what an inverted index stores for ranking (Mehran Ali);
  3. how to rank current vs superseded notices (Gaffar);
  4. how to compute Recall@k fairly (Basit Azam);
  5. heap vs sort for top-k (Gaffar).
- **Baseline design:** read every passage's tokens, count matching query terms, sort.
- **Planned index design:** custom hash table from term to a postings array.
- **Risks:**
  - paraphrased questions;
  - duplicate passages;
  - timing noise at the microsecond scale.
- **Agreed interfaces:**
  - `Corpus::load/add/remove`
  - `InvertedIndex::build/addPassage/removePassage/lookup`
  - `Retriever::search(Query, SearchOptions)`
  - `TextProcessor::tokenize/parseQuery`

## 4. Integration and peer-review record

| Module / file | Author | Reviewer | Review date | Issues found → fixed |
|---|---|---|---|---|
| `hash_table.h` | Mehran Ali | Waqas Ali | 21 Oct 2026 | [e.g. rehash must relink nodes, not copy them] |
| `inverted_index.*` | Mehran Ali | Gaffar | 22 Oct 2026 | [e.g. a repeated term in a passage created 2 postings → tf counter] |
| `top_k_heap.h`, `merge_sort.h` | Gaffar | Mehran Ali | 22 Oct 2026 | [ ] |
| `retriever.*` | Gaffar | Basit Azam | 23 Oct 2026 | [e.g. scan and index summed groups in a different order] |
| `text.*`, `corpus.*` | Basit Azam / Mehran Ali | Gaffar | 21 Oct 2026 | [ ] |
| `evaluation.cpp`, `tests.cpp`, `main.cpp`, GUI | Waqas Ali | Basit Azam | 25 Oct 2026 | [e.g. a test passage id clashed with a new MUET document id] |
| Integration test: `rag test` T15 (scan == index, 40/40) | Waqas Ali | All | 23 Oct 2026 | [ ] |

## 5. Progress / decision log

| # | Date | Decision or event | Reason | Decided by |
|---|---|---|---|---|
| 1 | 19 Oct 2026 | Separate chaining instead of open addressing | Updates need deletion; chaining keeps it simple | Mehran Ali, team |
| 2 | 20 Oct 2026 | Postings as growable arrays `{passage, tf}`, not linked nodes | Sequential traversal is faster; tf is needed for BM25 | Mehran Ali, Gaffar |
| 3 | 20 Oct 2026 | Same tokenizer for both engines; tokens precomputed at load | Fair comparison; the scan reads stored tokens, not raw text | Basit Azam, Waqas Ali |
| 4 | 22 Oct 2026 | Exact-duplicate folding via a normalised-text hash | D02-P1/D23-P1 appeared twice in the top 3 | Mehran Ali |
| 5 | 22 Oct 2026 | Evidence rule ≥ 50 % of concepts | Unanswerable "parking" question returned passages about "student" | Gaffar, team |
| 6 | 23 Oct 2026 | Freshness factor × 0.5 for superseded passages | Coverage ranker put the 2025 attendance rule first (T14) | Gaffar |
| 7 | 23 Oct 2026 | Small synonym list + report with and without it | Paraphrase questions Q06 and Q08 scored 0 | Basit Azam |
| 8 | 24 Oct 2026 | Time 40 searches per run, 15 runs, median | Single searches (~1 µs) are near clock resolution | Waqas Ali |
| 9 | 25 Oct 2026 | Add MUET CSE-context documents (D24–D31) and questions Q15–Q20 | Make the corpus match our own department; label it synthetic | Basit Azam, team |
| 10 | 25 Oct 2026 | Desktop GUI on top of `rag --json` | Easier live demo; retrieval logic stays in C++ | Waqas Ali |

## 6. Issue / task register

| Id | Task or issue | Owner | Opened | Closed | Notes |
|---|---|---|---|---|---|
| I-1 | Write 31 documents / 155 passages (incl. MUET CSE notices D24–D31) | Basit Azam | 19 Oct 2026 | 25 Oct 2026 | |
| I-2 | Label gold passages; cross-check | Basit Azam + Gaffar (checker) | 20 Oct 2026 | 24 Oct 2026 | See `data/DATASET.md` |
| I-3 | Hash table + collision tests | Mehran Ali | 20 Oct 2026 | 21 Oct 2026 | |
| I-4 | Heap / merge sort + top-k comparison | Gaffar | 21 Oct 2026 | 22 Oct 2026 | |
| I-5 | Paraphrase recall is low | Basit Azam + Gaffar | 23 Oct 2026 | 23 Oct 2026 | Synonyms + ablation |
| I-6 | Near-duplicates not folded | Mehran Ali | 22 Oct 2026 | open | Known limitation (T08) |
| I-7 | T20 failed after MUET data was added (test id clash) | Waqas Ali | 25 Oct 2026 | 25 Oct 2026 | Test passage renamed to TEST-P1 |
| I-8 | GUI layout: synonym checkbox cut off | Waqas Ali | 25 Oct 2026 | 25 Oct 2026 | Moved to the sample-question row |

## 7. Individual contribution notes

> **DRAFTS.** Each member must rewrite their own note in their own words and keep only what
> they actually did. The teacher may ask you to explain anything written here.

**Waqas Ali (25CS061):** I led the team and integrated the modules into one program. I wrote
the command-line interface, the evaluation mode that compares the scan with the index on 25,
50, 100 and 155 passages, and the 24-case test suite. I also built the desktop GUI for the
demo. I reviewed Mehran's hash table. One problem I solved was making the latency measurement
reliable: single searches were near the clock's resolution, so I timed batches and reported
medians. I learned how to check that two implementations give identical results.

**Mehran Ali (25CS009):** I implemented the separate-chaining hash table (FNV-1a hash,
resizing at load factor 0.75) and the inverted index with postings arrays, including adding,
updating and removing passages. I also wrote the passage store and the duplicate detection. I
tested the table with forced collisions (4 buckets, and a hash that puts every key in one
bucket). I reviewed Gaffar's heap. I learned why expected O(1) lookup can become O(n) in the
worst case.

**Gaffar (25CS067):** I wrote the bounded min-heap for top-k selection, the merge sort used for
comparison, and the retrieval logic: the linear-scan baseline, indexed search, the
coverage and BM25 + freshness rankers, the evidence rule and the tie-break. I showed that
coverage ranks the old 2025 attendance notice first, which is why we added the freshness rule.
I measured that the heap is about 4× faster than sorting all candidates. I reviewed Mehran's
inverted index.

**Basit Azam (25CS113):** I wrote the dataset (31 documents, 155 passages, including the
MUET CSE-context notices) and the 20 evaluation questions with gold labels. I also wrote the
tokenizer, the stop-word list, the suffix rules and the synonym list. I computed Recall@3 and
the with/without-synonyms comparison, and I documented the dataset in `DATASET.md`. I
reviewed Gaffar's retriever. I learned that keyword retrieval misses paraphrased questions and
why the gold labels must be written before looking at the engine's output.
