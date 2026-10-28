#include "retriever.h"

#include <cmath>
#include <cstdio>
#include <iomanip>
#include <ostream>

#include "merge_sort.h"
#include "top_k_heap.h"

const char* toString(Mode m) { return m == Mode::Scan ? "scan" : "index"; }
const char* toString(Ranker r) { return r == Ranker::Coverage ? "coverage" : "bm25f"; }
const char* toString(TopKMethod t) { return t == TopKMethod::Heap ? "heap" : "mergesort"; }

namespace {
int popcount64(uint64_t x) {
    int c = 0;
    while (x) {
        x &= x - 1;
        ++c;
    }
    return c;
}

struct BetterHit {
    const Corpus* corpus;
    bool operator()(const Hit& a, const Hit& b) const {
        if (a.score != b.score) return a.score > b.score;
        const Passage& pa = corpus->at(a.passage);
        const Passage& pb = corpus->at(b.passage);
        if (pa.superseded() != pb.superseded()) return !pa.superseded();
        if (pa.date != pb.date) return pa.date > pb.date;
        return a.passage < b.passage;
    }
};

bool passageHasAny(const Passage& p, const QueryGroup& g) {
    for (const auto& tok : p.tokens)
        for (const auto& t : g.terms)
            if (tok == t) return true;
    return false;
}
}  // namespace

double Retriever::bm25(int tf, size_t length, size_t df, size_t n, double avgLength) {
    const double k1 = 1.2, b = 0.75;
    const double idf = std::log(1.0 + (static_cast<double>(n) - static_cast<double>(df) + 0.5) /
                                          (static_cast<double>(df) + 0.5));
    const double norm = avgLength > 0 ? static_cast<double>(length) / avgLength : 1.0;
    return idf * (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * norm));
}

void Retriever::prepareScratch() const {
    const size_t n = corpus_.slots();
    if (total_.size() != n) {
        total_.assign(n, 0.0);
        groupBest_.assign(n, -1.0);
        mask_.assign(n, 0);
    }
    touched_.clear();
    groupTouched_.clear();
}

// Indexed retrieval: only the postings of the query terms are visited.
void Retriever::scoreIndexed(const Query& q) const {
    const size_t n = corpus_.liveCount();
    const double avg = corpus_.avgLength();
    for (size_t g = 0; g < q.groups.size(); ++g) {
        for (const std::string& term : q.groups[g].terms) {
            const std::vector<Posting>* list = index_.lookup(term);
            if (!list) continue;
            const size_t df = list->size();
            for (const Posting& post : *list) {
                const double c = bm25(post.tf, corpus_.at(post.passage).tokens.size(), df, n, avg);
                double& best = groupBest_[static_cast<size_t>(post.passage)];
                if (best < 0) groupTouched_.push_back(post.passage);
                if (c > best) best = c;
            }
        }
        for (int pid : groupTouched_) {
            const size_t i = static_cast<size_t>(pid);
            if (mask_[i] == 0) touched_.push_back(pid);
            mask_[i] |= (uint64_t{1} << g);
            total_[i] += groupBest_[i];
            groupBest_[i] = -1.0;
        }
        groupTouched_.clear();
    }
}

// Baseline: every live passage's token array is read for every query. Document
// frequencies are counted during the same pass, then the identical BM25 maths
// is applied.
void Retriever::scoreScan(const Query& q) const {
    struct Term {
        const std::string* text;
        size_t group;
    };
    std::vector<Term> terms;
    for (size_t g = 0; g < q.groups.size(); ++g)
        for (const auto& t : q.groups[g].terms) terms.push_back({&t, g});

    const size_t T = terms.size();
    std::vector<size_t> df(T, 0);
    std::vector<int> tf(T, 0);
    std::vector<int> candidates;
    std::vector<int> candTf;  // flattened candidates x T

    for (size_t i = 0; i < corpus_.slots(); ++i) {
        const Passage& p = corpus_.at(static_cast<int>(i));
        if (p.deleted) continue;
        bool any = false;
        for (const std::string& tok : p.tokens)
            for (size_t t = 0; t < T; ++t)
                if (tok == *terms[t].text) {
                    ++tf[t];
                    any = true;
                }
        if (any) {
            candidates.push_back(static_cast<int>(i));
            for (size_t t = 0; t < T; ++t) {
                candTf.push_back(tf[t]);
                if (tf[t] > 0) ++df[t];
                tf[t] = 0;
            }
        }
    }

    const size_t n = corpus_.liveCount();
    const double avg = corpus_.avgLength();
    for (size_t c = 0; c < candidates.size(); ++c) {
        const int pid = candidates[c];
        const size_t i = static_cast<size_t>(pid);
        const size_t len = corpus_.at(pid).tokens.size();
        touched_.push_back(pid);
        for (size_t g = 0; g < q.groups.size(); ++g) {
            double best = -1.0;
            for (size_t t = 0; t < T; ++t) {
                if (terms[t].group != g) continue;
                const int f = candTf[c * T + t];
                if (f > 0) {
                    const double s = bm25(f, len, df[t], n, avg);
                    if (s > best) best = s;
                }
            }
            if (best >= 0) {
                mask_[i] |= (uint64_t{1} << g);
                total_[i] += best;
            }
        }
    }
}

SearchResult Retriever::finalize(const Query& q, const SearchOptions& opt) const {
    SearchResult r;
    const double groups = static_cast<double>(q.groups.size());
    std::vector<Hit> hits;
    for (int pid : touched_) {
        const size_t i = static_cast<size_t>(pid);
        Hit h;
        h.passage = pid;
        h.matched = popcount64(mask_[i]);
        h.coverage = h.matched / groups;
        h.bm25 = total_[i];
        total_[i] = 0.0;
        mask_[i] = 0;
        ++r.candidates;
        if (h.coverage + 1e-12 < opt.minCoverage) {
            ++r.belowEvidenceRule;
            continue;
        }
        if (corpus_.isDuplicateOfOther(pid)) {
            ++r.duplicatesSuppressed;
            continue;
        }
        const Passage& p = corpus_.at(pid);
        h.score = opt.ranker == Ranker::Coverage ? h.coverage : h.bm25 * (p.superseded() ? 0.5 : 1.0);
        hits.push_back(h);
    }
    touched_.clear();

    BetterHit better{&corpus_};
    if (opt.topk == TopKMethod::Heap) {
        TopKHeap<Hit, BetterHit> heap(opt.k, better);
        for (const Hit& h : hits) heap.offer(h);
        r.hits = heap.takeBestFirst();
    } else {
        mergeSort(hits, better);
        if (hits.size() > opt.k) hits.resize(opt.k);
        r.hits = std::move(hits);
    }
    if (r.hits.empty()) {
        if (opt.k == 0)
            r.notice = "k = 0: no passages requested.";
        else if (r.candidates == 0)
            r.notice = "No passage contains any query term.";
        else
            r.notice = "Passages share some words with the query but none matches at least " +
                       std::to_string(static_cast<int>(opt.minCoverage * 100)) + "% of the query concepts.";
    }
    return r;
}

SearchResult Retriever::search(const Query& q, const SearchOptions& opt) const {
    if (corpus_.liveCount() == 0) {
        SearchResult r;
        r.notice = "The corpus is empty.";
        return r;
    }
    if (q.groups.empty()) {
        SearchResult r;
        r.notice = "The query is empty after preprocessing (blank or only stop words).";
        return r;
    }
    prepareScratch();
    if (opt.mode == Mode::Index)
        scoreIndexed(q);
    else
        scoreScan(q);
    return finalize(q, opt);
}

namespace {
std::string jsonString(const std::string& s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 32) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04x", c);
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
    return out + "\"";
}

std::string jsonList(const std::vector<std::string>& v) {
    std::string out = "[";
    for (size_t i = 0; i < v.size(); ++i) out += (i ? "," : "") + jsonString(v[i]);
    return out + "]";
}
}  // namespace

void printEvidenceJson(std::ostream& os, const Corpus& corpus, const Query& q, const SearchResult& r,
                       const SearchOptions& opt, double queryMicros) {
    os << std::setprecision(6);
    os << "{\"query\":" << jsonString(q.raw) << ",\"concepts\":[";
    for (size_t i = 0; i < q.groups.size(); ++i)
        os << (i ? "," : "") << "{\"term\":" << jsonString(q.groups[i].original)
           << ",\"expansions\":" << jsonList(std::vector<std::string>(q.groups[i].terms.begin() + 1, q.groups[i].terms.end()))
           << "}";
    os << "],\"mode\":\"" << toString(opt.mode) << "\",\"ranker\":\"" << toString(opt.ranker) << "\",\"topk\":\""
       << toString(opt.topk) << "\",\"k\":" << opt.k << ",\"candidates\":" << r.candidates
       << ",\"below_rule\":" << r.belowEvidenceRule << ",\"duplicates_folded\":" << r.duplicatesSuppressed
       << ",\"no_evidence\":" << (r.noEvidence() ? "true" : "false") << ",\"reason\":" << jsonString(r.notice)
       << ",\"query_us\":" << queryMicros << ",\"corpus_passages\":" << corpus.liveCount() << ",\"hits\":[";
    for (size_t i = 0; i < r.hits.size(); ++i) {
        const Hit& h = r.hits[i];
        const Passage& p = corpus.at(h.passage);
        std::vector<std::string> matched, missing, dups;
        for (const auto& g : q.groups) (passageHasAny(p, g) ? matched : missing).push_back(g.original);
        for (size_t j = 0; j < corpus.slots(); ++j) {
            const Passage& o = corpus.at(static_cast<int>(j));
            if (static_cast<int>(j) != h.passage && !o.deleted && o.canonical == h.passage) dups.push_back(o.id);
        }
        os << (i ? "," : "") << "{\"rank\":" << (i + 1) << ",\"id\":" << jsonString(p.id)
           << ",\"doc_id\":" << jsonString(p.docId) << ",\"title\":" << jsonString(p.title)
           << ",\"category\":" << jsonString(p.category) << ",\"version\":" << jsonString(p.version)
           << ",\"date\":" << jsonString(p.date) << ",\"status\":" << jsonString(p.status)
           << ",\"score\":" << h.score << ",\"bm25\":" << h.bm25 << ",\"matched_count\":" << h.matched
           << ",\"total_concepts\":" << q.groups.size() << ",\"matched\":" << jsonList(matched)
           << ",\"missing\":" << jsonList(missing) << ",\"duplicates\":" << jsonList(dups)
           << ",\"text\":" << jsonString(p.text) << "}";
    }
    os << "]}\n";
}

std::string excerpt(const std::string& text, size_t maxLen) {
    std::string clean;
    for (char c : text) clean.push_back((static_cast<unsigned char>(c) < 32) ? ' ' : c);
    if (clean.size() <= maxLen) return clean;
    size_t cut = clean.rfind(' ', maxLen);
    if (cut == std::string::npos || cut < maxLen / 2) cut = maxLen;
    return clean.substr(0, cut) + " ...";
}

void printEvidence(std::ostream& os, const Corpus& corpus, const Query& q, const SearchResult& r,
                   const SearchOptions& opt) {
    os << "Query: \"" << q.raw << "\"\n";
    os << "Concepts:";
    if (q.groups.empty()) os << " (none)";
    for (const auto& g : q.groups) {
        os << " [" << g.original;
        if (g.terms.size() > 1) {
            os << " ~";
            for (size_t i = 1; i < g.terms.size(); ++i) os << ' ' << g.terms[i];
        }
        os << ']';
    }
    os << "\nEngine: " << toString(opt.mode) << " | ranker: " << toString(opt.ranker)
       << " | top-k: " << toString(opt.topk) << " | k = " << opt.k << '\n';
    if (q.truncated) os << "Note: query had more than " << Query::kMaxGroups << " distinct terms; extra terms ignored.\n";

    if (r.noEvidence()) {
        os << "\nNo supported evidence found.\n  Reason: " << r.notice << "\n";
        return;
    }
    os << "Candidates: " << r.candidates << " (below evidence rule: " << r.belowEvidenceRule
       << ", duplicates folded: " << r.duplicatesSuppressed << ")\n\n";
    for (size_t i = 0; i < r.hits.size(); ++i) {
        const Hit& h = r.hits[i];
        const Passage& p = corpus.at(h.passage);
        os << '#' << (i + 1) << "  " << p.id << "   score " << std::fixed << std::setprecision(4) << h.score << '\n';
        os << "    Document : " << p.docId << " - " << p.title << " [" << p.category << "]\n";
        os << "    Source   : version " << p.version << ", dated " << p.date << ", status "
           << (p.superseded() ? "SUPERSEDED" : "CURRENT") << '\n';
        if (p.superseded())
            os << "    WARNING  : superseded version - NOT a verified current rule; check the newer notice.\n";
        os << "    Excerpt  : \"" << excerpt(p.text) << "\"\n";
        os << "    Why      : matched " << h.matched << '/' << q.groups.size() << " concepts (";
        bool first = true;
        std::string missing;
        for (const auto& g : q.groups) {
            if (passageHasAny(p, g)) {
                os << (first ? "" : ", ") << g.original;
                first = false;
            } else {
                missing += (missing.empty() ? "" : ", ") + g.original;
            }
        }
        os << ")";
        if (!missing.empty()) os << "; missing: " << missing;
        os << "; BM25 " << std::setprecision(3) << h.bm25;
        if (opt.ranker == Ranker::Bm25Fresh && p.superseded()) os << " x0.5 freshness";
        os << '\n';
        std::vector<std::string> dups;
        for (size_t j = 0; j < corpus.slots(); ++j) {
            const Passage& o = corpus.at(static_cast<int>(j));
            if (static_cast<int>(j) != h.passage && !o.deleted && o.canonical == h.passage) dups.push_back(o.id);
        }
        if (!dups.empty()) {
            os << "    Same text also in:";
            for (const auto& d : dups) os << ' ' << d;
            os << '\n';
        }
        os.unsetf(std::ios::floatfield);
    }
    os << "\n(Retrieved text is shown as untrusted, quoted data. It is never executed or obeyed as an instruction.)\n";
}
