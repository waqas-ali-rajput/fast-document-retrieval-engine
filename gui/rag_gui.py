"""Desktop GUI for the Fast Document Retrieval Engine (CS-251 PBL).

The GUI is only a front end: every search, ranking, test and benchmark is run
by the C++ program (rag.exe) and the GUI displays what it returns. No retrieval
logic lives in this file.

Run from the project folder:  python gui/rag_gui.py   (or run_gui.bat)
Needs only the Python standard library (tkinter).
"""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / ("rag.exe" if os.name == "nt" else "rag")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console flash

FONT = ("Segoe UI", 10)
MONO = ("Consolas", 10)
GREEN, RED, GREY, ACCENT = "#1f7a3a", "#b42318", "#667085", "#2f5bd3"

RANKERS = {"BM25 + freshness": "bm25f", "Concept coverage": "coverage"}
MODES = {"Inverted index": "index", "Linear scan (baseline)": "scan"}
TOPKS = {"Bounded heap": "heap", "Merge sort (all candidates)": "sort"}


def run_rag(args):
    """Run rag.exe with args from the project folder; return (exit code, stdout+stderr)."""
    proc = subprocess.run(
        [str(EXE), *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
    )
    return proc.returncode, proc.stdout + proc.stderr


def read_pipe_file(path, fields):
    rows = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("|")
            rows.append(parts + [""] * (fields - len(parts)))
    except OSError:
        pass
    return rows


class ReadOnlyText(tk.Text):
    """Text widget the user can select/copy from but not edit."""

    def __init__(self, master, **kw):
        super().__init__(master, wrap="word", borderwidth=0, highlightthickness=0, padx=12, pady=10, **kw)
        self.configure(state="disabled")

    def set(self, chunks):
        """chunks: list of (text, tags) tuples."""
        self.configure(state="normal")
        self.delete("1.0", "end")
        for text, tags in chunks:
            self.insert("end", text, tags)
        self.configure(state="disabled")
        self.yview_moveto(0.0)


def scrolled(parent, widget_cls, **kw):
    frame = ttk.Frame(parent)
    widget = widget_cls(frame, **kw)
    bar = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=bar.set)
    widget.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return frame, widget


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("University RAG Assistant - Document Retrieval Engine")
        self.geometry("1100x760")
        self.minsize(820, 560)
        self.configure(bg="#f5f6f8")

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(".", font=FONT)
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 15), background="#f5f6f8")
        style.configure("Sub.TLabel", foreground=GREY, background="#f5f6f8")
        style.configure("Status.TLabel", foreground=GREY)
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

        header = ttk.Frame(self, padding=(16, 12, 16, 4), style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Fast Document Retrieval Engine", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="CS-251 PBL  ·  retrieval runs in the C++ engine (rag.exe)  ·  "
                               "all documents are SYNTHETIC test data, not real university policy",
                  style="Sub.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(6, 0))
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel", padding=(16, 4)).pack(fill="x")

        self.build_search_tab()
        self.build_dataset_tab()
        self.build_output_tab("Tests", "Run all edge-case tests", ["test"], self.color_tests)
        self.build_output_tab("Evaluation", "Run full evaluation (about 10 s)", ["eval"], None, open_results=True)
        self.build_output_tab("Index stats", "Refresh", ["stats"], None)

        if not EXE.exists():
            self.after(200, self.offer_build)

    # ------------------------------------------------------------------ helpers
    def in_background(self, label, work, done):
        """Run work() in a thread, then done(result) on the UI thread."""
        self.status.set(label)
        self.config(cursor="watch")

        def target():
            try:
                result = work()
            except Exception as exc:  # shown to the user, never silently dropped
                result = exc
            self.after(0, lambda: self._finish(result, done))

        threading.Thread(target=target, daemon=True).start()

    def _finish(self, result, done):
        self.config(cursor="")
        if isinstance(result, Exception):
            self.status.set("Error.")
            messagebox.showerror("Error", str(result))
            return
        done(result)

    def offer_build(self):
        if not messagebox.askyesno("Engine not built",
                                   f"{EXE.name} was not found in\n{ROOT}\n\nBuild it now with build.bat? (needs g++)"):
            return

        def work():
            proc = subprocess.run(["cmd", "/c", "build.bat"], cwd=ROOT, capture_output=True, text=True,
                                  creationflags=NO_WINDOW)
            return proc.returncode, proc.stdout + proc.stderr

        def done(res):
            code, out = res
            if code == 0 and EXE.exists():
                self.status.set("Engine built.")
            else:
                self.status.set("Build failed.")
                messagebox.showerror("Build failed", out[-2000:])

        self.in_background("Building rag.exe ...", work, done)

    # ------------------------------------------------------------------ search tab
    def build_search_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="  Search  ")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x")
        self.question = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.question, font=("Segoe UI", 12))
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        entry.bind("<Return>", lambda _e: self.search())
        entry.focus_set()
        ttk.Button(row1, text="Search", style="Accent.TButton", command=self.search).pack(side="left", padx=(8, 0))
        ttk.Button(row1, text="Compare scan vs index", command=self.compare).pack(side="left", padx=(8, 0))

        row2 = ttk.Frame(tab, padding=(0, 8, 0, 0))
        row2.pack(fill="x")
        samples = [f"{q[0]} ({q[1]}): {q[2]}" for q in read_pipe_file(ROOT / "data" / "queries.txt", 5)]
        ttk.Label(row2, text="Sample question").pack(side="left")
        self.sample = ttk.Combobox(row2, values=samples, state="readonly", width=60)
        self.sample.pack(side="left", padx=(6, 14))
        self.sample.bind("<<ComboboxSelected>>", self.pick_sample)
        self.synonyms = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Synonym expansion", variable=self.synonyms).pack(side="left")

        row3 = ttk.Frame(tab, padding=(0, 8, 0, 6))
        row3.pack(fill="x")
        self.k = tk.IntVar(value=3)
        self.ranker = tk.StringVar(value="BM25 + freshness")
        self.mode = tk.StringVar(value="Inverted index")
        self.topk = tk.StringVar(value="Bounded heap")
        ttk.Label(row3, text="k").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=20, textvariable=self.k, width=4).pack(side="left", padx=(4, 14))
        for label, var, options, width in (("Ranker", self.ranker, RANKERS, 18), ("Engine", self.mode, MODES, 22),
                                           ("Top-k", self.topk, TOPKS, 24)):
            ttk.Label(row3, text=label).pack(side="left")
            ttk.Combobox(row3, textvariable=var, values=list(options), state="readonly", width=width).pack(
                side="left", padx=(4, 14))

        frame, self.results = scrolled(tab, ReadOnlyText, font=FONT, background="white")
        frame.pack(fill="both", expand=True)
        r = self.results
        r.tag_configure("h1", font=("Segoe UI Semibold", 13))
        r.tag_configure("rank", font=("Segoe UI Semibold", 12), foreground=ACCENT)
        r.tag_configure("bold", font=("Segoe UI Semibold", 10))
        r.tag_configure("muted", foreground=GREY)
        r.tag_configure("current", foreground="white", background=GREEN, font=("Segoe UI Semibold", 9))
        r.tag_configure("superseded", foreground="white", background=RED, font=("Segoe UI Semibold", 9))
        r.tag_configure("warn", foreground=RED, font=("Segoe UI Semibold", 10))
        r.tag_configure("quote", font=("Georgia", 11), lmargin1=18, lmargin2=18, spacing1=4, spacing3=4)
        r.tag_configure("good", foreground=GREEN)
        r.tag_configure("bad", foreground=RED)
        r.tag_configure("noev", font=("Segoe UI Semibold", 14), foreground=RED)
        r.tag_configure("rule", foreground="#d0d5dd")
        r.set([("Type a question and press Enter, or pick a sample question.\n\n", "h1"),
               ("Try: “minimum attendance required for the final examination” to see version handling,\n"
                "or “parking permit for student cars” to see the no-evidence answer.", "muted")])

    def pick_sample(self, _event):
        text = self.sample.get()
        self.question.set(text.split(": ", 1)[1] if ": " in text else text)
        self.search()

    def query_args(self, mode=None, time_runs=1):
        args = ["query", self.question.get(), "--json", "--k", str(max(1, int(self.k.get() or 3))),
                "--ranker", RANKERS[self.ranker.get()], "--mode", mode or MODES[self.mode.get()],
                "--topk", TOPKS[self.topk.get()], "--time-runs", str(time_runs)]
        if not self.synonyms.get():
            args.append("--no-synonyms")
        return args

    def parse_json(self, code, out):
        if code != 0:
            raise RuntimeError(out.strip() or f"rag.exe exited with code {code}")
        return json.loads(out)

    def search(self):
        if not self.question.get().strip():
            self.question.set("")
        args = self.query_args(time_runs=21)
        self.in_background("Searching ...", lambda: self.parse_json(*run_rag(args)), self.show_result)

    def compare(self):
        if not self.question.get().strip():
            messagebox.showinfo("Compare", "Type a question first.")
            return
        scan_args, index_args = self.query_args("scan", 201), self.query_args("index", 201)

        def work():
            return self.parse_json(*run_rag(scan_args)), self.parse_json(*run_rag(index_args))

        self.in_background("Timing both engines (201 runs each) ...", work, self.show_compare)

    def show_result(self, data, prefix=None):
        chunks = list(prefix or [])
        concepts = "  ".join(
            c["term"] + (" (~" + ", ".join(c["expansions"]) + ")" if c["expansions"] else "") for c in data["concepts"])
        chunks += [("Query concepts: ", "bold"), ((concepts or "(none)") + "\n", ""),
                   (f"{data['candidates']} candidate passages · {data['below_rule']} below the 50 % evidence rule · "
                    f"{data['duplicates_folded']} duplicates folded · {data['mode']} engine · {data['ranker']} ranker · "
                    f"{data['query_us']:.1f} µs (median)\n", "muted"),
                   ("─" * 70 + "\n", "rule")]
        if data["no_evidence"]:
            chunks += [("\nNo supported evidence found.\n", "noev"), (data["reason"] + "\n", "muted"),
                       ("\nThe engine refuses rather than inventing a university rule.\n", "muted")]
        for hit in data["hits"]:
            status_tag = "superseded" if hit["status"] == "superseded" else "current"
            chunks += [(f"\n#{hit['rank']}  {hit['id']}", "rank"), (f"    score {hit['score']:.4f}\n", "muted"),
                       (f"{hit['doc_id']} · {hit['title']}", "bold"), (f"   [{hit['category']}]\n", "muted"),
                       (f"Version {hit['version']} · dated {hit['date']}   ", "muted"),
                       (f" {hit['status'].upper()} ", status_tag), ("\n", "")]
            if hit["status"] == "superseded":
                chunks.append(("⚠ Superseded version: NOT a verified current rule. Check the newer notice.\n", "warn"))
            chunks.append((f"“{hit['text']}”\n", "quote"))
            chunks += [(f"Matched {hit['matched_count']}/{hit['total_concepts']}: ", "muted"),
                       (", ".join(hit["matched"]) or "-", "good")]
            if hit["missing"]:
                chunks += [("   Missing: ", "muted"), (", ".join(hit["missing"]), "bad")]
            chunks.append((f"   BM25 {hit['bm25']:.3f}" + (" × 0.5 freshness" if status_tag == "superseded"
                                                             and data["ranker"] == "bm25f" else "") + "\n", "muted"))
            if hit["duplicates"]:
                chunks.append(("Same text also in: " + ", ".join(hit["duplicates"]) + "\n", "muted"))
        if data["hits"]:
            chunks.append(("\nRetrieved text is shown as untrusted, quoted data; it is never obeyed as an instruction.\n",
                           "muted"))
        self.results.set(chunks)
        self.status.set(f"{len(data['hits'])} passage(s) returned from {data['corpus_passages']} indexed passages.")

    def show_compare(self, pair):
        scan, index = pair
        same = [h["id"] for h in scan["hits"]] == [h["id"] for h in index["hits"]]
        speed = scan["query_us"] / index["query_us"] if index["query_us"] else 0
        prefix = [("Linear scan vs inverted index\n", "h1"),
                  (f"Linear scan (baseline): {scan['query_us']:.2f} µs     Inverted index: {index['query_us']:.2f} µs"
                   f"     → index is {speed:.1f}× faster (median of 201 runs each)\n", "bold"),
                  ("Same ranked passages from both engines: ", ""),
                  ("YES\n" if same else "NO\n", "good" if same else "bad"),
                  ("For full repeatable benchmarks at 25 / 50 / 115 passages, use the Evaluation tab.\n\n", "muted")]
        self.show_result(index, prefix)
        self.status.set(f"Scan {scan['query_us']:.2f} µs vs index {index['query_us']:.2f} µs.")

    # ------------------------------------------------------------------ dataset tab
    def build_dataset_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="  Dataset  ")
        rows = read_pipe_file(ROOT / "data" / "passages.txt", 8)
        ttk.Label(tab, text=f"{len(rows)} passages from {len({r[1] for r in rows})} documents (synthetic). "
                            "Select a row to read the full passage.", style="Status.TLabel").pack(anchor="w")
        cols = ("id", "doc", "title", "category", "version", "date", "status")
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 6))
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=16)
        widths = (75, 50, 300, 105, 80, 110, 110)
        for col, width in zip(cols, widths):
            tree.heading(col, text=col.capitalize())
            tree.column(col, width=width, anchor="w", stretch=col == "title")
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        tree.tag_configure("superseded", foreground=RED)
        texts = {}
        for r in rows:
            item = tree.insert("", "end", values=r[:7], tags=("superseded",) if r[6] == "superseded" else ())
            texts[item] = r[7]
        detail = ReadOnlyText(tab, font=("Georgia", 11), height=4, background="white")
        detail.pack(fill="x")
        tree.bind("<<TreeviewSelect>>",
                  lambda _e: detail.set([(texts.get(tree.focus(), ""), "")]))

    # ------------------------------------------------------------------ output tabs
    def build_output_tab(self, name, button, args, colorizer, open_results=False):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text=f"  {name}  ")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 8))
        frame, text = scrolled(tab, ReadOnlyText, font=MONO, background="white")
        frame.pack(fill="both", expand=True)
        text.tag_configure("pass", foreground=GREEN)
        text.tag_configure("fail", foreground=RED, font=(MONO[0], MONO[1], "bold"))
        text.set([(f"Press “{button}”.", "")])

        def done(res):
            code, out = res
            text.set(colorizer(out) if colorizer else [(out, "")])
            self.status.set(f"{name}: finished (exit code {code}).")

        ttk.Button(bar, text=button, style="Accent.TButton",
                   command=lambda: self.in_background(f"{name}: running ...", lambda: run_rag(args), done)).pack(
            side="left")
        if open_results:
            ttk.Button(bar, text="Open results folder",
                       command=lambda: os.startfile(ROOT / "results") if os.name == "nt" else None).pack(
                side="left", padx=(8, 0))

    @staticmethod
    def color_tests(out):
        chunks = []
        for line in out.splitlines(keepends=True):
            tag = "pass" if "[PASS]" in line else "fail" if "[FAIL]" in line else ""
            chunks.append((line, tag))
        return chunks


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
        except Exception:
            pass
    App().mainloop()
