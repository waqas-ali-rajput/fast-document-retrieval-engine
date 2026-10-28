# Fast Document Retrieval Engine for a University RAG Assistant

CS-251 Data Structures and Algorithms: Problem-Based Learning task, 25CS.

This is the retrieval part of a RAG pipeline. It takes a question, finds candidate passages
in a corpus of academic text, ranks them, and returns a small, traceable evidence package: the
top-k passages with passage ID, document, version, date, status, an excerpt and the reason for
the score. It never calls an LLM. When no passage gives enough support, it prints
**"No supported evidence found."**

The data in `data/` is set in the Department of Computer Systems Engineering, MUET Jamshoro, but
every rule is **synthetic** test data, not official MUET policy. The one exception is D24, whose
facts come from the PBL task brief.

## Build

The only requirement is a C++17 compiler (tested with g++ 10.3 / TDM-GCC on Windows). No
third-party libraries are used.

In **PowerShell** (the default Windows terminal), go to the project folder first and put `.\`
in front of the commands:

```powershell
cd "D:\DSA PBL"
.\build.bat
.\rag.exe test
.\rag.exe query "minimum attendance required for the final examination"
```

In Command Prompt (cmd.exe), `build.bat` and `rag test` work without the `.\`.

Or with make / any POSIX shell:

```bash
make
```

You can also compile by hand:

```bash
g++ -std=c++17 -O2 -Wall -Wextra -o rag src/main.cpp src/text.cpp src/corpus.cpp src/inverted_index.cpp src/retriever.cpp src/evaluation.cpp src/tests.cpp
```

Run every command from the project folder so the program can find the `data/` paths.

## Run

| Command | What it does |
|---|---|
| `rag query "minimum attendance required for the final examination"` | One search; prints the evidence package |
| `rag query "cafeteria menu prices"` | Shows the "No supported evidence found" path |
| `rag query "CS-251 final examination date" --mode scan` | The same search with the linear-scan baseline |
| `rag query "late submission penalty" --ranker coverage --k 5` | Second ranking policy, larger k |
| `rag interactive` | Type questions one after another; a blank line quits |
| `rag test` | 24 edge-case / validation tests; writes `results/edge_case_tests.txt` |
| `rag eval` | Full evaluation: baseline vs index, both rankers, 25/50/100/155 passages, Recall@3, latency, memory, scaling, heap vs sort; writes `results/` |
| `rag stats` | Corpus, vocabulary, hash-table and memory figures |

Options: `--k N`, `--mode index|scan`, `--ranker bm25f|coverage`, `--topk heap|sort`,
`--min-coverage X`, `--no-synonyms`, `--data FILE`, `--json` (machine-readable output),
`--time-runs N` (median time of N repeated searches).

## Desktop GUI

Double-click **`run_gui.bat`**, or run this from the project folder:

```powershell
python gui\rag_gui.py
```

It needs only Python 3 with its built-in tkinter; there is nothing to install. If `rag.exe` is
missing, the GUI offers to build it.

The GUI is only a front end. Every search, ranking, test and benchmark still runs in the C++
engine (`rag.exe --json`). The GUI has these tabs:

- **Search** — ask a question, or pick one of the 20 labelled questions. Choose k, the ranker,
  the engine (index or scan) and the top-k method, and turn synonym expansion on or off.
  Results show provenance, a **CURRENT / SUPERSEDED** badge, matched and missing concepts, and
  the score. **Compare scan vs index** times both engines (201 runs each) and checks that they
  return the same passages.
- **Dataset** — every passage with its metadata; superseded ones are shown in red.
- **Tests** — runs `rag test`; PASS lines are green and FAIL lines red.
- **Evaluation** — runs `rag eval` and opens the `results/` folder.
- **Index stats** — vocabulary, hash-table and memory figures.

## Live demo checklist (brief section 14.5)

1. **Successful query:** `rag query "food and drinks in the computer laboratory"`. D02-P1 comes
   back with its provenance, and the identical repost D23-P1 is folded into it.
2. **No-evidence query:** `rag query "parking permit for student cars"`.
3. **Baseline vs index:** run the same question with `--mode scan` and `--mode index`. The
   results are identical. For timings, see `results/evaluation_summary.txt` (or run `rag eval`).
4. **Provenance and version handling:** `rag query "minimum attendance required for the final examination"`
   puts the 2026 notice first and marks the 2025 passages **SUPERSEDED**.

## Project layout

```
src/hash_table.h        custom separate-chaining hash table (FNV-1a, linked chains, resize at 0.75)  [student-built]
src/top_k_heap.h        custom bounded binary heap for top-k selection                             [student-built]
src/merge_sort.h        custom stable merge sort (sort-everything alternative)                     [student-built]
src/text.*              deterministic tokenizer, stop words, suffix rules, synonym expansion
src/corpus.*            passage store (array) + id hash + duplicate-text hash
src/inverted_index.*    term -> postings array {passage, tf}; add / remove / update
src/retriever.*         linear-scan baseline, indexed retrieval, 2 rankers, evidence printing
src/evaluation.cpp      `rag eval`
src/tests.cpp           `rag test`
src/main.cpp            command-line program
gui/rag_gui.py          desktop GUI (tkinter) that calls rag.exe --json
run_gui.bat             starts the GUI (builds rag.exe first if needed)
data/passages.txt       31 documents, 155 passages, 5 topics (MUET CSE context; synthetic except D24)
data/queries.txt        20 questions with gold passage labels
data/synonyms.txt       small query-expansion list
data/DATASET.md         dataset provenance and labelling notes
results/                generated by `rag eval` / `rag test`
docs/REPORT.md          technical / PBL report
docs/PROJECT_MANAGEMENT.md  team, work split, plan, logs, reviews, contribution notes (dates to complete)
docs/VIVA_GUIDE.md      viva preparation: overview, per-member Q&A, key numbers, demo script, PDF checklist
```

## Library use (declared as the brief requires)

The program uses `std::string` and `std::vector` as plain buffers, `<fstream>` for file input,
`<chrono>` for timing, and `std::sort` only to compute medians in the evaluation report. The
hash table, heap, merge sort, inverted index, ranking and top-k logic are written from scratch.
`std::unordered_map`, `std::map`, `std::priority_queue` and search libraries are not used.
