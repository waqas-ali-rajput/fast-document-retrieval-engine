// tests.cpp - repeatable edge-case and validation suite ("rag test").
// Every case records the expected and the observed behaviour; the table is
// printed and saved to results/edge_case_tests.txt.
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "app.h"
#include "corpus.h"
#include "inverted_index.h"
#include "merge_sort.h"
#include "retriever.h"
#include "text.h"
#include "top_k_heap.h"

namespace {
struct Case {
    std::string id, name, expected, observed;
    bool pass;
};

std::string ids(const Corpus& c, const SearchResult& r) {
    if (r.hits.empty()) return "no evidence";
    std::string s;
    for (const auto& h : r.hits) s += (s.empty() ? "" : ", ") + c.at(h.passage).id;
    return s;
}

int pos(const Corpus& c, const SearchResult& r, const std::string& id) {
    for (size_t i = 0; i < r.hits.size(); ++i)
        if (c.at(r.hits[i].passage).id == id) return static_cast<int>(i);
    return -1;
}

uint64_t constantHash(const std::string&) { return 42; }  // every key collides

bool sameHits(const SearchResult& a, const SearchResult& b) {
    if (a.hits.size() != b.hits.size()) return false;
    for (size_t i = 0; i < a.hits.size(); ++i)
        if (a.hits[i].passage != b.hits[i].passage || a.hits[i].score != b.hits[i].score) return false;
    return true;
}
}  // namespace

int runTests(const Paths& paths, std::ostream& out) {
    std::vector<Case> cases;
    auto record = [&](const std::string& id, const std::string& name, const std::string& expected,
                      const std::string& observed, bool pass) { cases.push_back({id, name, expected, observed, pass}); };

    std::string err;
    TextProcessor tp;
    tp.loadSynonyms(paths.synonyms, err);
    Corpus corpus;
    if (!corpus.load(paths.passages, tp, err)) {
        out << "Error: " << err << '\n';
        return 1;
    }
    InvertedIndex index;
    index.build(corpus);
    Retriever retriever(corpus, index);
    SearchOptions opt;  // index, bm25f, heap, k = 3

    // T01 empty corpus
    {
        Corpus empty;
        InvertedIndex ei;
        ei.build(empty);
        Retriever er(empty, ei);
        SearchResult r = er.search(tp.parseQuery("attendance"), opt);
        SearchOptions s = opt;
        s.mode = Mode::Scan;
        SearchResult r2 = er.search(tp.parseQuery("attendance"), s);
        record("T01", "Empty corpus", "No supported evidence (corpus is empty), both engines",
               r.notice + " / scan: " + r2.notice, r.noEvidence() && r2.noEvidence());
    }
    // T02 blank query
    {
        SearchResult a = retriever.search(tp.parseQuery("   "), opt);
        SearchResult b = retriever.search(tp.parseQuery("the of and is"), opt);
        record("T02", "Blank / stop-word-only query", "No supported evidence; query empty after preprocessing",
               a.notice + " | stop words only: " + ids(corpus, b), a.noEvidence() && b.noEvidence());
    }
    // T03 term not present
    {
        SearchResult r = retriever.search(tp.parseQuery("zebra quantum"), opt);
        record("T03", "Term not present", "No supported evidence, 0 candidates",
               ids(corpus, r) + ", candidates " + std::to_string(r.candidates), r.noEvidence() && r.candidates == 0);
    }
    // T04 repeated query terms
    {
        Query once = tp.parseQuery("attendance");
        Query thrice = tp.parseQuery("attendance attendance ATTENDANCE");
        SearchResult a = retriever.search(once, opt), b = retriever.search(thrice, opt);
        record("T04", "Repeated query terms", "Collapse to 1 concept; identical ranking to single term",
               std::to_string(thrice.groups.size()) + " concept(s); " + ids(corpus, b),
               thrice.groups.size() == 1 && sameHits(a, b));
    }
    // T05 repeated term inside a passage -> one posting with tf > 1
    {
        auto tfOf = [&](const std::string& term, const std::string& pid, int& postings) {
            int tf = 0;
            postings = 0;
            if (const auto* list = index.lookup(term))
                for (const auto& p : *list)
                    if (corpus.at(p.passage).id == pid) {
                        tf = p.tf;
                        ++postings;
                    }
            return tf;
        };
        int n1 = 0, n2 = 0;
        int tfAtt = tfOf("attendance", "D09-P1", n1);  // "attendance" occurs twice in D09-P1
        int tfFee = tfOf("fee", "D21-P4", n2);         // "fee" occurs twice in D21-P4
        record("T05", "Duplicate term occurrences in a passage", "One posting per passage with tf = 2",
               "D09-P1 'attendance': " + std::to_string(n1) + " posting, tf=" + std::to_string(tfAtt) +
                   "; D21-P4 'fee': " + std::to_string(n2) + " posting, tf=" + std::to_string(tfFee),
               n1 == 1 && tfAtt == 2 && n2 == 1 && tfFee == 2);
    }
    // T06 multiple matching passages, k respected, sorted
    {
        SearchResult r = retriever.search(tp.parseQuery("laboratory"), opt);
        bool sorted = true;
        for (size_t i = 1; i < r.hits.size(); ++i) sorted = sorted && r.hits[i - 1].score >= r.hits[i].score;
        record("T06", "Multiple matching passages", "Many candidates, exactly k = 3 returned, scores descending",
               std::to_string(r.candidates) + " candidates -> " + ids(corpus, r), r.candidates > 3 && r.hits.size() == 3 && sorted);
    }
    // T07 duplicate passages folded
    {
        SearchResult r = retriever.search(tp.parseQuery("food and drinks in the computer laboratory"), opt);
        bool both = pos(corpus, r, "D02-P1") >= 0 && pos(corpus, r, "D23-P1") >= 0;
        record("T07", "Exact duplicate passages (D02-P1 / D23-P1)", "Original shown once, repost folded",
               ids(corpus, r) + "; folded " + std::to_string(r.duplicatesSuppressed),
               pos(corpus, r, "D02-P1") == 0 && !both && r.duplicatesSuppressed >= 1);
    }
    // T08 near-duplicate is NOT folded (limitation made visible)
    {
        int a = corpus.findById("D02-P3"), b = corpus.findById("D23-P3");
        record("T08", "Near-duplicate (unauthorised/unauthorized)", "Not detected as duplicate (known limitation)",
               std::string("D23-P3 duplicate of D02-P3? ") + (corpus.at(b).canonical == a ? "yes" : "no"),
               corpus.at(b).canonical != a);
    }
    // T09 hash collisions: tiny fixed table
    {
        HashTable<int> small(4, false);
        for (int i = 0; i < 200; ++i) small.put("key" + std::to_string(i), i);
        bool ok = small.size() == 200;
        for (int i = 0; i < 200; ++i) {
            const int* v = small.find("key" + std::to_string(i));
            ok = ok && v && *v == i;
        }
        HashStats s = small.stats();
        record("T09", "Hash collisions (4 buckets, 200 keys, no resize)", "All 200 keys found with correct values",
               "max chain " + std::to_string(s.maxChain) + ", colliding entries " + std::to_string(s.collidingEntries),
               ok && s.collidingEntries == 196);
    }
    // T10 hash collisions: every key in one bucket, erase + reinsert
    {
        HashTable<int> one(8, true, constantHash);
        for (int i = 0; i < 50; ++i) one.put("t" + std::to_string(i), i);
        bool ok = one.erase("t10") && !one.contains("t10") && !one.erase("t10") && one.size() == 49;
        one.put("t10", 99);
        ok = ok && one.find("t10") && *one.find("t10") == 99 && *one.find("t49") == 49;
        HashStats s = one.stats();
        record("T10", "Worst-case hash (all keys same bucket)", "Chaining still correct for find/erase/insert",
               "used buckets " + std::to_string(s.usedBuckets) + ", longest chain " + std::to_string(s.maxChain), ok && s.usedBuckets == 1);
    }
    // T11 index built on a fully colliding table returns the same answers
    {
        InvertedIndex bad(2, false, constantHash);
        bad.build(corpus);
        Retriever br(corpus, bad);
        std::vector<LabelledQuery> qs;
        loadQueries(paths.queries, qs, err);
        bool ok = true;
        for (const auto& q : qs) ok = ok && sameHits(retriever.search(tp.parseQuery(q.text), opt), br.search(tp.parseQuery(q.text), opt));
        record("T11", "Index on degenerate hash (V terms in 1 chain)", "Same results as normal index for all " + std::to_string(qs.size()) + " labelled queries",
               std::string("identical: ") + (ok ? "yes" : "no") + ", longest chain " + std::to_string(bad.hashStats().maxChain),
               ok);
    }
    // T12 old/new versions: attendance
    {
        SearchResult r = retriever.search(tp.parseQuery("minimum attendance required for the final examination"), opt);
        int cur = pos(corpus, r, "D09-P1"), old = pos(corpus, r, "D04-P1");
        bool flagged = true;
        for (const auto& h : r.hits)
            if (corpus.at(h.passage).docId == "D04") flagged = flagged && corpus.at(h.passage).superseded();
        record("T12", "Old/new notice (attendance 2025 vs 2026)", "2026 notice ranked above 2025; 2025 marked SUPERSEDED",
               ids(corpus, r), cur >= 0 && (old < 0 || cur < old) && flagged);
    }
    // T13 old/new versions: date sheet
    {
        SearchResult r = retriever.search(tp.parseQuery("CS-251 final examination date"), opt);
        int cur = pos(corpus, r, "D20-P2"), old = pos(corpus, r, "D19-P2");
        record("T13", "Old/new date sheet (D19 vs D20)", "Revised D20-P2 ranked above original D19-P2", ids(corpus, r),
               cur >= 0 && (old < 0 || cur < old));
    }
    // T13b old/new versions: MUET registration notice (D28 original vs D29 revised)
    {
        SearchResult r = retriever.search(tp.parseQuery("last date for course registration fall 2026"), opt);
        int cur = pos(corpus, r, "D29-P1"), old = pos(corpus, r, "D28-P1");
        record("T13b", "Old/new registration notice (D28 vs D29)", "Revised D29-P1 first; D28-P1 below it if shown",
               ids(corpus, r), cur == 0 && (old < 0 || cur < old));
    }
    // T14 coverage ranker has no freshness rule (shows why the 2nd policy exists)
    {
        SearchOptions c = opt;
        c.ranker = Ranker::Coverage;
        SearchResult r = retriever.search(tp.parseQuery("minimum attendance required for the final examination"), c);
        record("T14", "Coverage ranker on version-sensitive query", "Superseded D04 passage can outrank current one",
               ids(corpus, r), !r.hits.empty() && corpus.at(r.hits[0].passage).superseded());
    }
    // T15 scan and index agree on every labelled query for both rankers
    {
        std::vector<LabelledQuery> qs;
        loadQueries(paths.queries, qs, err);
        int agree = 0, total = 0;
        for (Ranker rk : {Ranker::Coverage, Ranker::Bm25Fresh})
            for (const auto& q : qs) {
                SearchOptions a = opt, b = opt;
                a.ranker = b.ranker = rk;
                a.mode = Mode::Scan;
                ++total;
                if (sameHits(retriever.search(tp.parseQuery(q.text), a), retriever.search(tp.parseQuery(q.text), b))) ++agree;
            }
        record("T15", "Scan vs index consistency", "Identical ranked ids and scores for every labelled query, both rankers",
               std::to_string(agree) + "/" + std::to_string(total) + " identical", agree == total);
    }
    // T16 heap vs merge sort agree
    {
        std::vector<LabelledQuery> qs;
        loadQueries(paths.queries, qs, err);
        int agree = 0, total = 0;
        for (size_t k : {size_t{1}, size_t{3}, size_t{10}})
            for (const auto& q : qs) {
                SearchOptions a = opt, b = opt;
                a.k = b.k = k;
                a.minCoverage = b.minCoverage = 0.0;
                b.topk = TopKMethod::MergeSort;
                ++total;
                if (sameHits(retriever.search(tp.parseQuery(q.text), a), retriever.search(tp.parseQuery(q.text), b))) ++agree;
            }
        record("T16", "Heap top-k vs merge sort top-k", "Same top-k for k = 1, 3, 10 on every labelled query",
               std::to_string(agree) + "/" + std::to_string(total) + " identical", agree == total);
    }
    // T17 k larger than candidates, and k = 0
    {
        SearchOptions big = opt, zero = opt;
        big.k = 50;
        zero.k = 0;
        SearchResult r = retriever.search(tp.parseQuery("mobile phones examination hall"), big);
        SearchResult z = retriever.search(tp.parseQuery("mobile phones examination hall"), zero);
        record("T17", "k = 50 (> evidence) and k = 0", "Returns only qualifying passages; k = 0 returns none",
               std::to_string(r.hits.size()) + " hits for k=50; k=0 -> " + z.notice,
               r.hits.size() < 50 && !r.hits.empty() && z.noEvidence());
    }
    // T18 unanswerable questions
    {
        SearchResult a = retriever.search(tp.parseQuery("parking permit for student cars"), opt);
        SearchResult b = retriever.search(tp.parseQuery("cafeteria menu prices"), opt);
        record("T18", "Unanswerable questions", "No supported evidence found (no invented rule)",
               "parking: " + ids(corpus, a) + " (" + std::to_string(a.candidates) + " weak candidates); cafeteria: " +
                   ids(corpus, b),
               a.noEvidence() && b.noEvidence());
    }
    // T19 untrusted passage text is data, not a command
    {
        SearchResult inj = retriever.search(tp.parseQuery("ignore previous instructions attendance"), opt);
        SearchResult after = retriever.search(tp.parseQuery("minimum attendance required for the final examination"), opt);
        record("T19", "Prompt-injection text in a passage (D22-P3)", "Returned only as quoted data; later answers unchanged",
               "injection query -> " + ids(corpus, inj) + "; attendance query still -> " + ids(corpus, after),
               pos(corpus, inj, "D22-P3") >= 0 && pos(corpus, after, "D09-P1") >= 0);
    }
    // T20 add, update and remove a passage after the index is built
    do {
        Corpus c2;
        c2.load(paths.passages, tp, err);
        InvertedIndex i2;
        i2.build(c2);
        Retriever r2(c2, i2);
        Passage p{"TEST-P1", "TEST", "Transport Notice (test)", "notice", "v1", "2026-10-20", "current",
                  "Parking permits for student cars are issued by the transport office.", {}, -1, false};
        int idx = c2.add(p, tp);
        if (idx < 0) {
            record("T20", "Add / update / remove after indexing", "Test passage id must be unused",
                   "TEST-P1 already exists in the corpus", false);
            break;
        }
        i2.addPassage(idx, c2.at(idx));
        SearchResult added = r2.search(tp.parseQuery("parking permit for student cars"), opt);

        // update = remove old version + index the new text under the same id
        i2.removePassage(idx, c2.at(idx));
        c2.remove(idx);
        p.version = "v2";
        p.text = "Vehicle stickers for student cars are issued by the security office.";
        int idx2 = c2.add(p, tp);
        i2.addPassage(idx2, c2.at(idx2));
        SearchResult oldText = r2.search(tp.parseQuery("parking permit transport"), opt);
        SearchResult newText = r2.search(tp.parseQuery("vehicle stickers security office"), opt);

        i2.removePassage(idx2, c2.at(idx2));
        c2.remove(idx2);
        SearchResult removed = r2.search(tp.parseQuery("vehicle stickers security office"), opt);
        bool ok = pos(c2, added, "TEST-P1") == 0 && oldText.noEvidence() && pos(c2, newText, "TEST-P1") == 0 &&
                  removed.noEvidence() && i2.lookup("sticker") == nullptr;
        record("T20", "Add / update / remove after indexing", "New passage found; old text gone after update; nothing after removal",
               "added -> " + ids(c2, added) + "; old text -> " + ids(c2, oldText) + "; new text -> " + ids(c2, newText) +
                   "; removed -> " + ids(c2, removed),
               ok);
    } while (false);
    // T21 duplicate passage_id rejected
    {
        const size_t before = corpus.slots();
        Passage dup{"D01-P1", "D01", "x", "course", "v", "2026-01-01", "current", "duplicate id", {}, -1, false};
        const bool rejected = corpus.add(dup, tp) < 0;
        record("T21", "Duplicate passage_id", "Rejected at ingestion", rejected ? "rejected" : "accepted",
               rejected && corpus.findById("D01-P1") == 0 && corpus.slots() == before);
    }
    // T22 deterministic tie-break
    {
        SearchOptions c = opt;
        c.ranker = Ranker::Coverage;
        SearchResult r = retriever.search(tp.parseQuery("laboratory"), c);
        bool ordered = true;
        for (size_t i = 1; i < r.hits.size(); ++i) {
            const Passage& a = corpus.at(r.hits[i - 1].passage);
            const Passage& b = corpus.at(r.hits[i].passage);
            if (r.hits[i - 1].score == r.hits[i].score && a.superseded() == b.superseded())
                ordered = ordered && (a.date > b.date || (a.date == b.date && r.hits[i - 1].passage < r.hits[i].passage));
        }
        SearchResult again = retriever.search(tp.parseQuery("laboratory"), c);
        record("T22", "Tie-break on equal scores", "Newer date first, then file order; repeat runs identical",
               ids(corpus, r), ordered && sameHits(r, again));
    }
    // T23 student-built heap and merge sort on raw integers
    {
        auto greater = [](int a, int b) { return a > b; };
        TopKHeap<int, decltype(greater)> h(3, greater);
        for (int v : {5, 1, 9, 3, 9, 7, 2}) h.offer(v);
        std::vector<int> top = h.takeBestFirst();
        std::vector<int> all = {5, 1, 9, 3, 9, 7, 2};
        mergeSort(all, [](int a, int b) { return a < b; });
        std::ostringstream os;
        os << "heap top-3 " << top[0] << ',' << top[1] << ',' << top[2] << "; sorted";
        for (int v : all) os << ' ' << v;
        record("T23", "Heap and merge sort unit check", "top-3 = 9,9,7; sorted = 1 2 3 5 7 9 9", os.str(),
               top == std::vector<int>({9, 9, 7}) && all == std::vector<int>({1, 2, 3, 5, 7, 9, 9}));
    }

    std::ostringstream table;
    int passed = 0;
    table << "Edge-case and validation tests (" << cases.size() << " cases)\n";
    table << "=====================================================================\n";
    for (const auto& c : cases) {
        if (c.pass) ++passed;
        table << c.id << "  [" << (c.pass ? "PASS" : "FAIL") << "]  " << c.name << "\n      expected: " << c.expected
              << "\n      observed: " << c.observed << "\n";
    }
    table << "=====================================================================\n";
    table << passed << '/' << cases.size() << " passed\n";

    std::filesystem::create_directories(paths.results);
    std::ofstream(paths.results + "/edge_case_tests.txt") << table.str();
    out << table.str();
    return passed == static_cast<int>(cases.size()) ? 0 : 1;
}
