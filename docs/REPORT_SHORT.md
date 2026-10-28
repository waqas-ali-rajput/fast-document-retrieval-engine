# Fast Document Retrieval Engine for a University RAG Assistant
### Short Report with Program Output: CS-251 Data Structures and Algorithms (25CS)
### Department of Computer Systems Engineering, Mehran University of Engineering and Technology, Jamshoro

**Team:** Waqas Ali (25CS061) · Mehran Ali (25CS009) · Gaffar (25CS067) · Basit Azam (25CS113)
**Subject teacher:** Dr. Ali Asghar Manjotho · **Submitted:** [date]

> The full technical report is `docs/REPORT.md`. Every screenshot below was taken from our
> program on 26 Oct 2026 (Windows 11, g++ 10.3 `-O2`). The data is set in MUET's CSE department
> but, apart from D24 (the PBL brief), every rule is **synthetic** and not official MUET policy.

## 1. What we built

The **retrieval** step of a RAG assistant. Given a question, the program returns the top-k
passages with their source (passage id, document, version, date, CURRENT/SUPERSEDED status).
If there is not enough support, it answers **"No supported evidence found."**

- **Data:** 31 documents, 155 passages, 5 topics; 20 labelled questions (8 keyword,
  4 paraphrase, 5 version/ambiguous, 3 unanswerable).
- **Baseline:** a linear scan that reads every token of every passage, O(T·q).
- **Index:** our own **hash table** (separate chaining, FNV-1a, resize at load 0.75) maps each
  word to a **postings list** `{passage, tf}`. A search only visits the postings of the
  question's words, O(q + P).
- **Ranking:** BM25 + freshness (superseded passages × 0.5), or simple coverage.
  **Evidence rule:** at least 50 % of the question's concepts must match.
- **Top-k:** our own bounded **min-heap**, O(C log k); merge sort, O(C log C), for comparison.
- **Front ends:** the command-line program `rag.exe` and a desktop GUI that calls it.

## 2. Key results

| Measure | Result |
|---|---|
| Recall@3 (155 passages, 17 answerable questions) | **0.912** (0.794 without synonyms) |
| Unanswerable questions refused | **3 / 3** |
| Scan vs index, 155 passages | 16.75 µs vs 1.49 µs (about **11×**) |
| Scan vs index, 15,500 passages | 1,900 µs vs 130 µs (about **15×**) |
| Index memory, 155 passages | 64 KB |
| Heap vs merge sort (C = 9,700, k = 3) | 0.68 ms vs 2.54 ms, same top-k |
| Scan and index give identical results | YES, every question, ranker and size |
| Tests | **24 / 24 pass** |

## 3. Program output: command line

![Build and a normal query. The current 2026 attendance notice (75 %) ranks first; the old 2025 notice matches more words (BM25 10.593) but is SUPERSEDED, so the freshness rule halves its score and it drops below.](../Screenshots/Screenshot 2026-10-26 212706.png)

![The same query timed over 201 runs: median 2.8 µs. A single first run (47.7 µs above) is slower because the program has just started.](../Screenshots/Screenshot 2026-10-26 212736.png)

![Unanswerable question. Passages share the word "student", but none matches 50 % of the concepts, so the program refuses instead of inventing a rule.](../Screenshots/Screenshot 2026-10-26 212755.png)

![Linear-scan baseline (--mode scan). The revised date sheet D20-P2 is returned first, with its source and the reason for its score.](../Screenshots/Screenshot 2026-10-26 212814.png)

![Coverage ranker with k = 5 and synonym expansion (submission ~ submit, penalty ~ fine). The superseded D28 notice is flagged with a warning.](../Screenshots/Screenshot 2026-10-26 212842.png)

![Interactive mode: 155 passages and 670 unique terms loaded.](../Screenshots/Screenshot 2026-10-26 212904.png)

## 4. Program output: tests (`rag test`)

![Tests T01-T13: empty corpus, blank query, missing word, repeated words, duplicates, hash collisions (4 buckets / 200 keys; all keys in one bucket; whole index in one chain of 670) and old/new notices.](../Screenshots/Screenshot 2026-10-26 212921.png)

![Tests T14-T23: scan = index (40/40), heap = merge sort (60/60), k limits, unanswerable questions, injection text, add/update/remove, duplicate id, tie-break. Result: 24/24 passed.](../Screenshots/Screenshot 2026-10-26 212952.png)

## 5. Program output: evaluation (`rag eval`)

![Evaluation at 25 passages, coverage ranker: index memory 18.6 KB; Recall@3 0.833; unanswerable refused 3/3; scan 3.17 µs vs index 0.52 µs.](../Screenshots/Screenshot 2026-10-26 213037.png)

![25 passages with BM25 + freshness, then 50 passages (coverage): every row shows "same? yes" (scan and index agree).](../Screenshots/Screenshot 2026-10-26 213057.png)

![50 passages: Recall@3 0.800 for both rankers; scan 4.6 µs vs index 0.79 µs.](../Screenshots/Screenshot 2026-10-26 213126.png)

![100 passages: 1,024 buckets, longest chain 4; Recall@3 0.875; scan 9.98 µs vs index 1.26 µs.](../Screenshots/Screenshot 2026-10-26 213150.png)

![100 passages (BM25 + freshness) and the full 155-passage corpus: index memory 64.0 KB, load factor 0.65, longest chain 4.](../Screenshots/Screenshot 2026-10-26 213205.png)

![155 passages: Recall@3 0.912 for both rankers; scan 16.75 µs vs index 1.49 µs; identical results everywhere ("YES"). Without synonyms Recall@3 drops to 0.794.](../Screenshots/Screenshot 2026-10-26 213224.png)

![Scaling to 15,500 passages: the speed-up grows from 10.1× to 14.6×. Bounded heap vs merge sort with 9,700 candidates: 679 µs vs 2,536 µs, same top-k.](../Screenshots/Screenshot 2026-10-26 213240.png)

![rag stats: 155 passages, 1,557 tokens, 670 terms, 1,501 postings; index built in 0.235 ms; 65,520 bytes of index memory.](../Screenshots/Screenshot 2026-10-26 213306.png)

## 6. Program output: desktop GUI

![Search tab: a sample question with provenance, CURRENT badge, and matched/missing concepts.](../Screenshots/Screenshot 2026-10-26 213336.png)

![Compare scan vs index (median of 201 runs each): the index is 6.9× faster and both engines return the same ranked passages.](../Screenshots/Screenshot 2026-10-26 213357.png)

![Dataset tab: all 155 passages with metadata; superseded passages are shown in red.](../Screenshots/Screenshot 2026-10-26 213418.png)

![Tests tab: the same 24 tests, 24/24 passed.](../Screenshots/Screenshot 2026-10-26 213434.png)

![Evaluation tab: runs rag eval inside the GUI.](../Screenshots/Screenshot 2026-10-26 213452.png)

![Index stats tab: vocabulary, hash-table health and memory figures.](../Screenshots/Screenshot 2026-10-26 213503.png)

## 7. Conclusion

- The inverted index returns **exactly the same answers** as the linear scan, and is about
  **11× faster** at 155 passages and **15×** at 15,500. The gap grows with corpus size.
- The **freshness rule** puts current notices above superseded ones; the **evidence rule**
  makes the program refuse unanswerable questions instead of guessing.
- **Limitations:**
  - Keyword search misses paraphrases without synonyms (0.794).
  - Near-duplicates are not folded.
  - Version status is entered by hand.
  - The MUET documents are synthetic.
- Timings differ slightly from run to run (about ±10 %); the trends are stable.
