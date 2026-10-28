# Viva preparation guide
**CS-251 PBL · Fast Document Retrieval Engine · MUET CSE · batch 25CS**
Waqas Ali (25CS061) · Mehran Ali (25CS009) · Gaffar (25CS067) · Basit Azam (25CS113)

---

## 1. The 1-minute explanation (everyone should be able to say this)

> "A RAG assistant first has to **find** the right passages before an LLM can answer. Our
> project is that finding step.
>
> We store 155 passages from 31 documents. For every passage we keep its ID, document, version,
> date and whether it is current or superseded. We built two search methods:
> - a **linear scan** that reads every passage for every question;
> - an **inverted index**: our own **hash table** maps each word to a **postings list** of the
>   passages containing it.
>
> Candidates are scored with **BM25 plus a freshness rule**, so old notices go down. We pick the
> top k with our own **min-heap**. If fewer than half of the question's words match, we say
> **'No supported evidence found'** instead of inventing an answer.
>
> Both methods return identical results, but the index is about **12× faster** at 155 passages
> and about **18× faster** at 15,500. Recall@3 is **0.91**, and all 3 unanswerable questions
> are refused."

---

## 2. How one question flows through the program

Example question: **"minimum attendance required for the final examination"**

1. **Preprocess** (`text.cpp`)
   - Lower-case the text, split on punctuation and drop stop words ("the", "for").
   - Strip a trailing "s".
   - Concepts: `minimum, attendance, required, final, examination`.
2. **Look up each word** in the hash table (`inverted_index.cpp`).
   - Each lookup takes O(1) on average.
   - It returns the postings list for that word, e.g. `attendance → [D04-P1 tf1, D04-P2 tf1, …, D09-P1 tf2, …]`.
3. **Score candidates** (`retriever.cpp`). For every passage in those lists:
   - record which concepts it matched (a bitmask);
   - add up its BM25 weights.
4. **Evidence rule:** keep only passages that match at least 50 % of the concepts. Here, 37
   candidates become 3.
5. **Duplicates:** if two passages have exactly the same text, show only one of them.
6. **Freshness:** superseded passages (the 2025 notice D04) get score × 0.5.
7. **Top-k:** a min-heap of size k = 3 keeps the best 3 (`top_k_heap.h`).
8. **Output:**
   - #1 is D09-P1, the 2026 notice (75 %), marked CURRENT;
   - #2 and #3 are the 2025 passages, marked SUPERSEDED with a warning;
   - each result shows the matched and missing words.

The linear scan does steps 3–8 the same way. The only difference is step 2: instead of looking
words up, it reads **all 1,557 tokens** of the corpus.

---

## 3. What each member must know (and likely questions)

### Waqas Ali (25CS061): integration, testing, evaluation, GUI

**Files:** `main.cpp`, `evaluation.cpp`, `tests.cpp`, `gui/rag_gui.py`.

- **Q: How did you measure latency fairly?**
  Same machine, same questions, same k and ranker for both methods. For each question: 5
  warm-up runs, then 15 measured runs. Each run times 40 searches back to back and divides by
  40, because one search takes about 1 µs, which is close to the clock's resolution. We report
  the **median**, because it ignores occasional spikes from Windows background work. Index
  build time is measured separately.
- **Q: How do you know the index gives correct answers?**
  Test T15 runs all 20 questions through both the scan and the index with both rankers. The
  passage IDs and scores match **40/40**. `rag eval` checks the same thing at every corpus
  size.
- **Q: What does Recall@3 mean?**
  The number of correct passages in the top 3, divided by all correct passages for that
  question. Q09 has 2 correct passages and we return 1 of them, so its Recall@3 = 0.5. We
  average this over the 17 answerable questions: **0.912**.
- **Q: Why is the evaluation done at 25, 50, 100 and 155 passages?**
  The brief asks for 3 increasing sizes (about 25, 50 and 100); 155 is our full corpus. We also
  copied the corpus up to 15,500 passages to show how the two methods scale (speed only).
- **Q: What does the GUI do? Does it contain search logic?**
  No. It runs `rag.exe --json` and only displays the results. All the data structures are in
  C++.
- **Q: Which edge cases did you test?** See the T01–T23 table in report §6. Know at least:
  - empty corpus;
  - blank query;
  - word not present;
  - repeated words;
  - duplicates;
  - collisions;
  - old/new notices.

### Mehran Ali (25CS009): hash table and inverted index

**Files:** `hash_table.h`, `inverted_index.*`, `corpus.*`.

- **Q: How does your hash table work?**
  - An array of buckets. Each bucket is a **singly linked list** of nodes `{key, value, next}`
    (separate chaining).
  - Hash function: **FNV-1a** (start from a fixed offset; for each character, XOR it in, then
    multiply by a prime). Bucket = hash % bucketCount.
- **Q: How do you handle collisions?**
  Keys that land in the same bucket go into that bucket's linked list. Lookup walks the list
  comparing keys.
  - Test T09: 200 keys in 4 buckets, all found correctly.
  - Test T10: a hash function that sends every key to one bucket; still correct, just slow.
- **Q: What is the load factor and when do you resize?**
  Load factor = entries / buckets. When it would go above **0.75**, we **double** the bucket
  array and relink every node into its new bucket. Nodes are not copied, only re-linked. Each
  resize costs O(n), but averaged over all inserts it is **amortised O(1)**. At 155 passages:
  1,024 buckets, load 0.65, longest chain 4.
- **Q: Why chaining instead of open addressing?**
  Deletion is easy, which we need for updating passages. The table never "fills up". It is
  simple to get right.
- **Q: What is stored in a postings list? Why tf?**
  An array of `{passage index, tf}`, where tf is how many times the word appears in that
  passage. BM25 needs tf. The list's length is the **df** (how many passages contain the word),
  which BM25 also needs.
- **Q: What if a word appears twice in one passage?**
  Still **one** posting, with tf = 2 (test T05). Because one passage's words are indexed
  together, its posting is always the last one in the list, so we just increment its tf.
- **Q: How do you add or update a passage?**
  - **Add:** append to the store, then append a posting to each of its words' lists.
  - **Update:** remove the old passage's postings from each list, mark the old slot deleted,
    then index the new text (test T20).
- **Q: Complexity?**
  - Build: O(T) expected, where T = total tokens.
  - Lookup: O(1) expected, O(V) worst case (all words in one chain).
  - Memory: O(V + T).
- **Q: How much memory does the index use?**
  64 KB at 155 passages:
  - 8 KB bucket array;
  - 41.9 KB nodes;
  - 14.1 KB postings.

  The text itself is counted separately (93 KB).

### Gaffar (25CS067): search, ranking and top-k

**Files:** `retriever.*`, `top_k_heap.h`, `merge_sort.h`.

- **Q: What are your two ranking methods?**
  - **Coverage** = matched concepts ÷ total concepts. Simple and explainable.
  - **BM25 + freshness:**
    - Rare words count more (idf).
    - Repeating a word helps, but with diminishing returns (tf saturation).
    - Long passages are normalised.
    - Superseded passages are multiplied by 0.5.
- **Q: Explain BM25 in simple words.**
  For each query word: `idf × tf·(k1+1) / (tf + k1·(1 − b + b·len/avg_len))`, with k1 = 1.2 and
  b = 0.75.
  - **idf** is high for rare words like "scholarship" and low for common words like "student".
  - The tf part grows with repetition but levels off.
  - The length part stops long passages from winning just by being long.
- **Q: Why did you need the freshness rule?**
  With coverage, the question "minimum attendance required…" ranks the **2025 notice first**,
  because that passage matches 4 of 5 words. That old rule (70 %) is wrong now (test T14). With
  freshness, the **2026 notice (75 %) comes first** and the old one is marked SUPERSEDED.
- **Q: What is your tie-break?**
  1. higher score;
  2. current before superseded;
  3. newer date;
  4. earlier position in the file.

  Repeated runs always give the same order (test T22).
- **Q: How does your heap select the top k?**
  It is a binary heap stored in an array with **at most k elements**, and its **root is the
  worst** of the kept elements. For each candidate: if the heap has fewer than k elements,
  insert it (sift up). Otherwise, if the candidate is better than the root, replace the root
  and sift down. At the end, pop everything to get the results in order.
- **Q: Heap vs sorting: complexity and when the heap wins?**
  - Heap: **O(C log k)** time, O(k) space.
  - Merge sort of all candidates: **O(C log C)** time, O(C) space.
  - The heap wins when k is much smaller than C. Measured at 15,500 passages with
    C = 9,700 candidates: heap 0.71 ms vs sort 2.98 ms. Both give the same top-k (test T16).
  - Sorting only makes sense if you need the whole ranked list.
- **Q: How is the linear scan different from the index?**
  - The scan reads every token of every passage: **O(T × q)**.
  - The index only visits the postings of the query words: **O(q + P)**.
  - The scoring code afterwards is the same, which is why the results are identical.
- **Q: What is the evidence rule?**
  A passage must match **at least 50 % of the question's concepts**. Otherwise "parking permit
  for student cars" would return passages that just contain "student" (46 weak candidates →
  0 evidence).

### Basit Azam (25CS113): dataset, questions, preprocessing

**Files:** `data/*`, `text.*`.

- **Q: What is in your dataset?**
  - 31 documents and 155 passages in 5 topics (course, lab, exam, notice, admissions), in the
    context of MUET's CSE department.
  - Each passage has an ID, document ID, title, category, version, date and status.
  - Everything is **synthetic and labelled as such**, except D24, whose facts come from our
    PBL brief. We did not claim any rule is official MUET policy (brief §10).
- **Q: Why synthetic?** The brief allows synthetic data if it is labelled clearly. We had no
  official MUET documents, and using made-up rules lets us plant test cases:
  - old/new notices;
  - exact duplicates;
  - a near-duplicate;
  - an injection passage.
- **Q: What kinds of questions did you create?**
  20 questions:
  - 8 keyword;
  - 4 paraphrase;
  - 5 ambiguous/version;
  - 3 unanswerable.

  The brief asks for at least 4/3/3/2 (12 in total).
- **Q: How did you label the correct passages?**
  By reading the whole corpus, **before** looking at what the engine returned. Only current
  passages count as correct. Gaffar cross-checked the labels, and the disagreements are
  recorded in `DATASET.md`.
- **Q: What preprocessing do you do?**
  1. Split on non-alphanumeric characters, so "CS-251" becomes "cs" + "251".
  2. Lower-case everything.
  3. Remove 77 stop words.
  4. "-ies" → "-y"; drop a trailing "s".

  Both methods use exactly the same preprocessing.
- **Q: Why does keyword search fail on paraphrases?**
  "Can I eat lunch in the computer room" shares almost no words with "Food and drinks are
  prohibited in the computer laboratories". Our small synonym list (eat → food,
  room → laboratory) fixes this; without it, Recall@3 drops from 0.912 to 0.794. We say
  honestly that the list was written while looking at our own data.

---

## 4. General questions anyone may be asked

| Question | Short answer |
|---|---|
| What is RAG? | Retrieval-Augmented Generation: first **retrieve** relevant passages, then an LLM **generates** an answer from them. We built the retrieval part. |
| What is an inverted index? | A map from each **word** to the list of **passages containing it**: the reverse of passage → words. |
| Why not `std::unordered_map` / `std::priority_queue`? | The brief forbids them as a substitute for the parts we claim to have built; we wrote our own hash table and heap. `std::vector` and `std::string` are used only as plain buffers, which the brief allows. |
| Which 3+ course concepts did you combine? | Hashing (hash table), arrays/postings and linked lists (chains), heap (top-k), sorting (merge sort), searching (linear scan vs index lookup). |
| Is the index always better? | No. It uses extra memory (64 KB here) and build time (about 0.2 ms), and on 25 passages it saves only about 3 µs. It wins clearly as the collection grows. |
| What does "No supported evidence found" protect against? | The assistant inventing a university rule when there is no source. |
| How do you treat the injection passage D22-P3? | As plain data: it is printed in quotes, never executed or obeyed (test T19). |
| What are your limitations? | Paraphrases; crude suffix rules; near-duplicates not detected; a fixed 50 % threshold; version status set by hand; speed-up at large sizes measured on a copied corpus. |
| What would you improve? | A bigger synonym list or embeddings; phrase matching; near-duplicate detection; automatic "replaces" links between notices; compressed postings. |
| Worst case of your hash table? | Every key in one bucket → lookup O(V). Test T11 builds the whole index like that: answers stay correct (670 terms in one chain), it is just slower. |

---

## 5. Key numbers to remember

| Item | Value |
|---|---|
| Documents / passages / topics | 31 / 155 / 5 |
| Tokens T / unique terms V / postings | 1,557 / 670 / 1,501 |
| Questions | 20 (8 keyword, 4 paraphrase, 5 version/ambiguous, 3 unanswerable) |
| Recall@3 (155 passages) | **0.912** with synonyms, 0.794 without |
| Unanswerable correctly refused | **3 / 3** |
| Scan vs index at 155 passages | 17.7 µs vs 1.5 µs (about 12×) |
| Scan vs index at 15,500 passages | 2,257 µs vs 126 µs (about 18×) |
| Index memory at 155 passages | 64 KB |
| Heap vs merge sort (C = 9,700) | 0.71 ms vs 2.98 ms |
| Tests | **24 / 24 pass** |
| Hash table at 155 passages | 1,024 buckets, load 0.65, longest chain 4 |

---

## 6. Live demo script (about 4 minutes; brief §14.5)

Open with `run_gui.bat`, or in cmd: `cd /d "D:\DSA PBL"`.

1. **Successful query:** *food and drinks in the computer laboratory*. D02-P1 is first, and
   the line "Same text also in: D23-P1" shows the duplicate.
2. **Provenance and versions:** *minimum attendance required for the final examination*. The
   2026 notice is CURRENT; the 2025 notices are SUPERSEDED, with a warning.
3. **MUET example:** *last date for course registration fall 2026*. The revised notice D29
   comes before the original D28.
4. **No evidence:** *parking permit for student cars* gives "No supported evidence found".
5. **Baseline vs index:** click **Compare scan vs index**. It shows both times and "Same
   ranked passages: YES".
6. **Tests tab:** run them and show 24/24 PASS.
7. (If asked) **Evaluation tab:** show the Recall@3 and latency tables.

---

## 7. Check against the PDF (brief sections 9–15)

| PDF requirement | Status | Where |
|---|---|---|
| §9.1 Passages with passage_id, document_id, title/category, source/version/date, text; metadata kept through to the output | ✅ | `data/passages.txt`, every result |
| §9.2 Same preprocessing for both methods; repeated terms and empty queries shown | ✅ | `text.cpp`, T02, T04 |
| §9.3 Linear scan + our own inverted index (hash table + postings); collisions, duplicates, updates explained | ✅ | `retriever.cpp`, `inverted_index.*`, report §2–3, T09–T11, T20 |
| §9.4 At least 3 course concepts integrated; at least 2 main components built ourselves; no ready-made search library | ✅ | hash table + heap + merge sort |
| §9.5 Two ranking methods on the same candidates; fixed tie-break; top-k using a course algorithm; heap vs sort explained | ✅ | report §4, §8; T14, T16, T22 |
| §9.6 Configurable top-k with IDs; no-match handling; superseded marked; documents treated as untrusted data | ✅ | `--k`, T01–T03, T12–T13b, T18, T19 |
| §9.7 One repeatable evaluation command running both methods | ✅ | `rag eval` |
| C++17; forbidden STL containers not used for the claimed parts; library use declared | ✅ | README "Library use" |
| §10 At least 20 documents, at least 100 passages, at least 4 topics; synthetic data labelled; no private data | ✅ | 31 / 155 / 5 |
| §10 At least 12 questions (at least 4 keyword, 3 paraphrase, 3 ambiguous/version, 2 unanswerable), gold labels | ✅ | 20 questions |
| §10 Labels cross-checked, disagreements recorded | ⚠️ **team** | `DATASET.md` table: confirm Gaffar really checked them |
| §10 Three corpus sizes (about 25 / 50 / 100) | ✅ | 25 / 50 / 100 (+155) |
| §10 Minimum edge cases, with expected and observed results | ✅ | `results/edge_case_tests.txt` |
| §11 Median latency (at least 10 runs after warm-up), build time kept separate | ✅ | report §7.1 |
| §11 Recall@3 + unanswerable count reported separately | ✅ | report §7.2 |
| §11 Index memory with the method stated; index vs text kept separate | ✅ | report §7.4 |
| §11 Complexity in terms of N, T, V, P, C; expected vs worst-case hashing | ✅ | report §8 |
| §11 Honest reflection on successes and failures | ✅ | report §7.2, §9, §10 |
| §12 Dated milestone plan | ✅ | `PROJECT_MANAGEMENT.md` §2 (19–25 Oct 2026) |
| §12 Responsibilities for each member | ✅ | `PROJECT_MANAGEMENT.md` §1 |
| §12 Progress/decision log (at least 3 entries) | ✅ | 10 dated entries |
| §12 Code integration / peer review evidence | ⚠️ **team** | §4 table: dates filled; write what each review actually found |
| §12 Test ownership record | ✅ | §1 table |
| §12 Contribution note from each member | ⚠️ **team** | §7 drafts: each member rewrites their own |
| §14.1 Runnable code + README, works offline | ✅ | `build.bat`, README |
| §14.2 Dataset + questions + labels + provenance | ✅ | `data/` |
| §14.3 Report, 7–12 pages | ✅ (Markdown) | `docs/REPORT.md`: convert to Word/PDF if the teacher wants that format |
| §14.4 Project-management evidence | ⚠️ **team** | review notes and contribution notes as above |
| §14.5 Live demo; each member answers questions about their part | ⚠️ **team** | section 6 script; practise sections 1–3 |

---

## 8. Before submission: final checklist

- [x] Remove the API key file from the project folder (done).
- [x] Dates filled in (19–25 Oct 2026); confirm the team agrees with them.
- [ ] Each member rewrites their contribution note (§7) in their own words.
- [ ] Adjust the work split (§1) if anyone actually did different parts.
- [ ] Convert `docs/REPORT.md` to Word/PDF if required.
- [ ] Every member runs `build.bat`, `rag test` and the GUI on their own laptop once.
- [ ] Every member reads their own files and can explain them without notes.
- [ ] Follow the naming and submission instructions the teacher gives.
