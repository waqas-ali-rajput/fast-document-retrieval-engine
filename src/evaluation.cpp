// evaluation.cpp - repeatable evaluation mode ("rag eval").
//
// Runs the same labelled questions through the scan baseline and the inverted
// index, with both ranking policies, on corpora of about 25, 50 and all 115
// passages; reports Recall@3, unanswerable handling, median query latency,
// index build time and index memory; then a runtime-only scaling run on a
// replicated corpus and a heap-vs-merge-sort top-k comparison.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>

#include "app.h"
#include "corpus.h"
#include "inverted_index.h"
#include "retriever.h"
#include "text.h"

namespace {
using Clock = std::chrono::steady_clock;

volatile size_t g_sink = 0;  // keeps timed work from being optimised away

std::vector<std::string> splitChar(const std::string& s, char sep) {
    std::vector<std::string> parts;
    std::string cur;
    for (char c : s) {
        if (c == sep) {
            parts.push_back(cur);
            cur.clear();
        } else if (c != '\r') {
            cur.push_back(c);
        }
    }
    parts.push_back(cur);
    return parts;
}

double median(std::vector<double> v) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());  // library sort is fine for reporting statistics
    size_t m = v.size() / 2;
    return v.size() % 2 ? v[m] : (v[m - 1] + v[m]) / 2.0;
}

// Median over `runs` measured runs (after `warmup` runs) of the mean time of
// `reps` back-to-back searches, in microseconds.
double medianQueryMicros(const Retriever& r, const Query& q, const SearchOptions& o, int warmup = 5, int runs = 15,
                         int reps = 40) {
    for (int i = 0; i < warmup; ++i) g_sink = g_sink + r.search(q, o).hits.size();
    std::vector<double> samples;
    for (int run = 0; run < runs; ++run) {
        auto t0 = Clock::now();
        for (int i = 0; i < reps; ++i) g_sink = g_sink + r.search(q, o).hits.size();
        auto t1 = Clock::now();
        samples.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count() / reps);
    }
    return median(samples);
}

double medianBuildMillis(const Corpus& c, int runs = 7) {
    std::vector<double> samples;
    for (int i = 0; i < runs; ++i) {
        auto t0 = Clock::now();
        InvertedIndex idx;
        idx.build(c);
        auto t1 = Clock::now();
        g_sink = g_sink + idx.vocabularySize();
        samples.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
    }
    return median(samples);
}

std::string hitIds(const Corpus& c, const SearchResult& r) {
    if (r.hits.empty()) return "NO-EVIDENCE";
    std::string s;
    for (const auto& h : r.hits) s += (s.empty() ? "" : " ") + c.at(h.passage).id;
    return s;
}

// Gold passage g counts as retrieved if it, or the passage it duplicates, was returned
// (duplicates are folded into one result by design).
double recallAtK(const Corpus& c, const SearchResult& r, const std::vector<std::string>& gold) {
    if (gold.empty()) return 0.0;
    size_t found = 0;
    for (const auto& gid : gold) {
        int gi = c.findById(gid);
        for (const auto& h : r.hits) {
            if (h.passage == gi || (gi >= 0 && c.at(gi).canonical == h.passage)) {
                ++found;
                break;
            }
        }
    }
    return static_cast<double>(found) / static_cast<double>(gold.size());
}

bool sameResults(const SearchResult& a, const SearchResult& b) {
    if (a.hits.size() != b.hits.size()) return false;
    for (size_t i = 0; i < a.hits.size(); ++i)
        if (a.hits[i].passage != b.hits[i].passage || std::abs(a.hits[i].score - b.hits[i].score) > 1e-9) return false;
    return true;
}

std::string fmt(double v, int prec = 2) {
    std::ostringstream os;
    os << std::fixed << std::setprecision(prec) << v;
    return os.str();
}

std::string kb(size_t bytes) { return fmt(static_cast<double>(bytes) / 1024.0, 1) + " KB"; }
}  // namespace

bool loadQueries(const std::string& path, std::vector<LabelledQuery>& out, std::string& error) {
    std::ifstream in(path);
    if (!in) {
        error = "cannot open queries file: " + path;
        return false;
    }
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#' || line == "\r") continue;
        std::vector<std::string> f = splitChar(line, '|');
        if (f.size() < 4) {
            error = "bad query line: " + line;
            return false;
        }
        LabelledQuery q{f[0], f[1], f[2], {}, f.size() > 4 ? f[4] : ""};
        if (f[3] != "-" && !f[3].empty()) q.gold = splitChar(f[3], ',');
        out.push_back(q);
    }
    return true;
}

int runEvaluation(const Paths& paths, std::ostream& out) {
    std::string err;
    std::vector<LabelledQuery> queries;
    if (!loadQueries(paths.queries, queries, err)) {
        out << "Error: " << err << '\n';
        return 1;
    }
    TextProcessor tp;
    if (!tp.loadSynonyms(paths.synonyms, err)) out << "Warning: " << err << " (continuing without synonyms)\n";

    std::filesystem::create_directories(paths.results);
    std::ofstream qcsv(paths.results + "/query_results.csv");
    std::ofstream lcsv(paths.results + "/latency.csv");
    std::ofstream scsv(paths.results + "/scaling.csv");
    std::ostringstream rep;  // summary report (also printed)

    qcsv << "corpus_size,query_id,type,mode,ranker,synonyms,returned_top3,gold_in_subset,recall_at_3,no_evidence,"
            "unanswerable_correct,candidates\n";
    lcsv << "corpus_size,query_id,mode,ranker,median_query_us\n";
    scsv << "passages,replication,build_ms,vocabulary,postings,index_kb,scan_median_us,index_median_us,speedup\n";

    rep << "=====================================================================\n";
    rep << " Fast Document Retrieval Engine - evaluation report\n";
    rep << "=====================================================================\n";
    rep << "Corpus file  : " << paths.passages << "\nQueries file : " << paths.queries << " (" << queries.size()
        << " questions)\nk = 3, evidence rule: >= 50% of query concepts matched\n";
    rep << "Latency: 5 warm-up runs, then 15 measured runs of 40 back-to-back searches; median reported.\n\n";

    const size_t sizes[] = {25, 50, 100, static_cast<size_t>(-1)};
    const Ranker rankers[] = {Ranker::Coverage, Ranker::Bm25Fresh};
    const Mode modes[] = {Mode::Scan, Mode::Index};
    bool allConsistent = true;

    for (size_t limit : sizes) {
        Corpus corpus;
        if (!corpus.load(paths.passages, tp, err, limit)) {
            out << "Error: " << err << '\n';
            return 1;
        }
        InvertedIndex index;
        index.build(corpus);
        Retriever retriever(corpus, index);
        const std::string sizeLabel = std::to_string(corpus.liveCount());
        const IndexMemory mem = index.memory();
        const HashStats hs = index.hashStats();

        rep << "---------------------------------------------------------------------\n";
        rep << "Corpus size: " << corpus.liveCount() << " passages, " << corpus.totalTokens() << " tokens (T), "
            << index.vocabularySize() << " unique terms (V), " << mem.postingCount << " postings\n";
        rep << "Index build time (median of 7): " << fmt(medianBuildMillis(corpus), 3) << " ms\n";
        rep << "Index memory: buckets " << kb(mem.bucketArray) << " + nodes " << kb(mem.nodes) << " + long keys "
            << kb(mem.keyHeap) << " + postings " << kb(mem.postings) << " = " << kb(mem.total()) << '\n';
        rep << "Document storage (not index): text+metadata " << kb(corpus.documentTextBytes())
            << ", token arrays " << kb(corpus.tokenStorageBytes()) << '\n';
        rep << "Hash table: " << hs.buckets << " buckets, load " << fmt(hs.loadFactor) << ", longest chain "
            << hs.maxChain << ", colliding entries " << hs.collidingEntries << ", resizes " << hs.resizes << "\n\n";

        rep << std::left << std::setw(5) << "Q" << std::setw(13) << "type" << std::setw(10) << "ranker"
            << std::setw(31) << "index top-3" << std::setw(8) << "R@3" << std::setw(11) << "scan us" << std::setw(11)
            << "index us" << "same?\n";

        for (Ranker rk : rankers) {
            double recallSum = 0;
            int answerable = 0, unansCorrect = 0, unansTotal = 0;
            std::vector<double> scanTimes, indexTimes;
            for (const auto& lq : queries) {
                Query q = tp.parseQuery(lq.text);
                std::vector<std::string> gold;
                for (const auto& g : lq.gold)
                    if (corpus.findById(g) >= 0) gold.push_back(g);
                const bool unanswerable = lq.gold.empty();

                SearchResult res[2];
                double micros[2];
                for (int m = 0; m < 2; ++m) {
                    SearchOptions o;
                    o.mode = modes[m];
                    o.ranker = rk;
                    res[m] = retriever.search(q, o);
                    micros[m] = medianQueryMicros(retriever, q, o);
                    lcsv << sizeLabel << ',' << lq.id << ',' << toString(modes[m]) << ',' << toString(rk) << ','
                         << fmt(micros[m], 3) << '\n';
                    const double rc = recallAtK(corpus, res[m], gold);
                    qcsv << sizeLabel << ',' << lq.id << ',' << lq.type << ',' << toString(modes[m]) << ','
                         << toString(rk) << ",on," << hitIds(corpus, res[m]) << ',' << gold.size() << ','
                         << (gold.empty() ? std::string("n/a") : fmt(rc, 3)) << ','
                         << (res[m].noEvidence() ? "yes" : "no") << ','
                         << (unanswerable ? (res[m].noEvidence() ? "yes" : "no") : "n/a") << ',' << res[m].candidates
                         << '\n';
                }
                scanTimes.push_back(micros[0]);
                indexTimes.push_back(micros[1]);
                const bool same = sameResults(res[0], res[1]);
                allConsistent = allConsistent && same;

                std::string recallText = "n/a";
                if (unanswerable) {
                    ++unansTotal;
                    if (res[1].noEvidence()) ++unansCorrect;
                    recallText = res[1].noEvidence() ? "ok" : "WRONG";
                } else if (!gold.empty()) {
                    double rc = recallAtK(corpus, res[1], gold);
                    recallSum += rc;
                    ++answerable;
                    recallText = fmt(rc);
                }
                rep << std::setw(5) << lq.id << std::setw(13) << lq.type << std::setw(10) << toString(rk)
                    << std::setw(31) << hitIds(corpus, res[1]) << std::setw(8) << recallText << std::setw(11)
                    << fmt(micros[0], 2) << std::setw(11) << fmt(micros[1], 2) << (same ? "yes" : "NO") << '\n';
            }
            rep << ">> " << toString(rk) << " @ " << sizeLabel << " passages: average Recall@3 = "
                << (answerable ? fmt(recallSum / answerable, 3) : std::string("n/a")) << " over " << answerable
                << " answerable questions (with gold in subset); unanswerable correctly refused " << unansCorrect << '/'
                << unansTotal << "; median query time scan " << fmt(median(scanTimes), 2) << " us vs index "
                << fmt(median(indexTimes), 2) << " us\n\n";
        }
    }
    rep << "Scan and index returned identical ranked results for every query/ranker/size: "
        << (allConsistent ? "YES" : "NO - investigate") << "\n\n";

    // Synonym ablation on the full corpus.
    {
        TextProcessor plain;
        plain.setUseSynonyms(false);
        Corpus corpus;
        corpus.load(paths.passages, plain, err);
        InvertedIndex index;
        index.build(corpus);
        Retriever retriever(corpus, index);
        rep << "---------------------------------------------------------------------\n";
        rep << "Ablation: synonym expansion OFF (full corpus, index engine)\n";
        for (Ranker rk : rankers) {
            double sum = 0;
            int n = 0, refused = 0, unans = 0;
            std::string perQuery;
            for (const auto& lq : queries) {
                SearchOptions o;
                o.ranker = rk;
                SearchResult r = retriever.search(plain.parseQuery(lq.text), o);
                qcsv << corpus.liveCount() << ',' << lq.id << ',' << lq.type << ",index," << toString(rk)
                     << ",off," << hitIds(corpus, r) << ',' << lq.gold.size() << ','
                     << (lq.gold.empty() ? std::string("n/a") : fmt(recallAtK(corpus, r, lq.gold), 3)) << ','
                     << (r.noEvidence() ? "yes" : "no") << ','
                     << (lq.gold.empty() ? (r.noEvidence() ? "yes" : "no") : "n/a") << ',' << r.candidates << '\n';
                if (lq.gold.empty()) {
                    ++unans;
                    if (r.noEvidence()) ++refused;
                    continue;
                }
                double rc = recallAtK(corpus, r, lq.gold);
                sum += rc;
                ++n;
                perQuery += " " + lq.id + "=" + fmt(rc);
            }
            rep << ">> " << toString(rk) << ": average Recall@3 = " << fmt(sum / n, 3) << " (" << n
                << " answerable), unanswerable refused " << refused << '/' << unans << "\n   per query:" << perQuery
                << "\n";
        }
        rep << '\n';
    }

    // Runtime-only scaling run: the corpus is replicated with a unique marker token per
    // copy so copies are not folded as duplicates. Relevance labels do not apply here.
    rep << "---------------------------------------------------------------------\n";
    rep << "Scaling (runtime only, replicated corpus, bm25f, k = 3, median over all " << queries.size() << " queries)\n";
    rep << std::left << std::setw(10) << "passages" << std::setw(11) << "build ms" << std::setw(8) << "V"
        << std::setw(10) << "postings" << std::setw(12) << "index KB" << std::setw(12) << "scan us" << std::setw(12)
        << "index us" << "speed-up\n";
    const int reps[] = {1, 10, 50, 100};
    for (int rf : reps) {
        Corpus base;
        base.load(paths.passages, tp, err);
        Corpus big;
        for (int copy = 0; copy < rf; ++copy) {
            for (size_t i = 0; i < base.slots(); ++i) {
                Passage p = base.at(static_cast<int>(i));
                if (copy > 0) {
                    p.id += "~r" + std::to_string(copy);
                    p.text += " copy" + std::to_string(copy);
                }
                big.add(p, tp);
            }
        }
        const double buildMs = medianBuildMillis(big, 5);
        InvertedIndex index;
        index.build(big);
        Retriever retriever(big, index);
        std::vector<double> scanT, idxT;
        for (const auto& lq : queries) {
            Query q = tp.parseQuery(lq.text);
            SearchOptions o;
            o.mode = Mode::Scan;
            scanT.push_back(medianQueryMicros(retriever, q, o, 2, 9, rf >= 50 ? 3 : 15));
            o.mode = Mode::Index;
            idxT.push_back(medianQueryMicros(retriever, q, o, 2, 9, rf >= 50 ? 3 : 15));
        }
        const double s = median(scanT), x = median(idxT);
        const IndexMemory mem = index.memory();
        rep << std::setw(10) << big.liveCount() << std::setw(11) << fmt(buildMs, 3) << std::setw(8)
            << index.vocabularySize() << std::setw(10) << mem.postingCount << std::setw(12)
            << fmt(mem.total() / 1024.0, 1) << std::setw(12) << fmt(s, 2) << std::setw(12) << fmt(x, 2)
            << fmt(x > 0 ? s / x : 0, 1) << "x\n";
        scsv << big.liveCount() << ',' << rf << ',' << fmt(buildMs, 3) << ',' << index.vocabularySize() << ','
             << mem.postingCount << ',' << fmt(mem.total() / 1024.0, 1) << ',' << fmt(s, 3) << ',' << fmt(x, 3) << ','
             << fmt(x > 0 ? s / x : 0, 2) << '\n';
    }
    rep << '\n';

    // Top-k policy comparison: bounded heap O(C log k) vs merge sort of all candidates O(C log C).
    rep << "---------------------------------------------------------------------\n";
    rep << "Top-k selection: bounded heap vs merge sort of all candidates (index engine, bm25f, broad query,\n"
           "minCoverage 0 so every candidate is ranked)\n";
    {
        Corpus base;
        base.load(paths.passages, tp, err);
        Corpus big;
        for (int copy = 0; copy < 100; ++copy)
            for (size_t i = 0; i < base.slots(); ++i) {
                Passage p = base.at(static_cast<int>(i));
                if (copy > 0) {
                    p.id += "~r" + std::to_string(copy);
                    p.text += " copy" + std::to_string(copy);
                }
                big.add(p, tp);
            }
        InvertedIndex index;
        index.build(big);
        Retriever retriever(big, index);
        Query broad = tp.parseQuery("students course examination laboratory fee semester");
        const size_t ks[] = {3, 10, 100};
        for (size_t k : ks) {
            SearchOptions h, m;
            h.k = m.k = k;
            h.minCoverage = m.minCoverage = 0.0;
            h.topk = TopKMethod::Heap;
            m.topk = TopKMethod::MergeSort;
            SearchResult rh = retriever.search(broad, h), rm = retriever.search(broad, m);
            const double th = medianQueryMicros(retriever, broad, h, 2, 9, 5);
            const double tm = medianQueryMicros(retriever, broad, m, 2, 9, 5);
            rep << "  " << big.liveCount() << " passages, C = " << rh.candidates << " candidates, k = " << std::setw(4)
                << k << ": heap " << fmt(th, 1) << " us, merge sort " << fmt(tm, 1) << " us, same top-k: "
                << (sameResults(rh, rm) ? "yes" : "NO") << '\n';
        }
    }
    rep << "\nCSV files written to " << paths.results << "/ (query_results.csv, latency.csv, scaling.csv)\n";

    std::ofstream(paths.results + "/evaluation_summary.txt") << rep.str();
    out << rep.str();
    return allConsistent ? 0 : 2;
}
