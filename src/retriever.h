// retriever.h - the two retrieval architectures and two ranking policies.
//
// Architectures (identical preprocessing and scoring maths):
//   Mode::Scan   baseline - reads every stored passage's tokens for every query
//   Mode::Index  looks query terms up in the inverted index and touches only
//                the postings of those terms
// Ranking policies (same candidate set for both):
//   Ranker::Coverage   score = matched query concepts / total query concepts
//   Ranker::Bm25Fresh  BM25 term weighting (k1 = 1.2, b = 0.75), summed over
//                      concepts, multiplied by 0.5 for superseded passages
// Evidence rule: a passage is only evidence if it matches at least half of the
// query concepts (minCoverage). Nothing above the rule -> "No supported
// evidence found". Exact/normalised duplicates are reported once.
// Deterministic tie-break: higher score, then current before superseded, then
// newer source date, then lower passage array index (= file order).
#pragma once

#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <string>
#include <vector>

#include "corpus.h"
#include "inverted_index.h"
#include "text.h"

enum class Mode { Scan, Index };
enum class Ranker { Coverage, Bm25Fresh };
enum class TopKMethod { Heap, MergeSort };

const char* toString(Mode m);
const char* toString(Ranker r);
const char* toString(TopKMethod t);

struct SearchOptions {
    size_t k = 3;
    Mode mode = Mode::Index;
    Ranker ranker = Ranker::Bm25Fresh;
    TopKMethod topk = TopKMethod::Heap;
    double minCoverage = 0.5;
};

struct Hit {
    int passage = -1;
    double score = 0.0;
    double bm25 = 0.0;
    double coverage = 0.0;
    int matched = 0;
};

struct SearchResult {
    std::vector<Hit> hits;
    size_t candidates = 0;            // passages matching at least one concept
    size_t belowEvidenceRule = 0;     // candidates rejected by minCoverage
    size_t duplicatesSuppressed = 0;  // duplicate passages folded into their original
    std::string notice;               // explanation when there are no hits
    bool noEvidence() const { return hits.empty(); }
};

class Retriever {
public:
    Retriever(const Corpus& corpus, const InvertedIndex& index) : corpus_(corpus), index_(index) {}
    SearchResult search(const Query& q, const SearchOptions& opt) const;

    static double bm25(int tf, size_t length, size_t df, size_t n, double avgLength);

private:
    const Corpus& corpus_;
    const InvertedIndex& index_;

    // Per-query scratch arrays indexed by passage; reset through touched_.
    mutable std::vector<double> total_;
    mutable std::vector<double> groupBest_;
    mutable std::vector<uint64_t> mask_;
    mutable std::vector<int> touched_;
    mutable std::vector<int> groupTouched_;

    void prepareScratch() const;
    void scoreIndexed(const Query& q) const;
    void scoreScan(const Query& q) const;
    SearchResult finalize(const Query& q, const SearchOptions& opt) const;
};

// Human-readable evidence package (stdout). Passage text is printed as quoted
// data only; nothing in a passage is ever interpreted as a command.
void printEvidence(std::ostream& os, const Corpus& corpus, const Query& q, const SearchResult& r,
                   const SearchOptions& opt);
std::string excerpt(const std::string& text, size_t maxLen = 150);

// The same evidence package as one JSON object (used by the GUI front end).
void printEvidenceJson(std::ostream& os, const Corpus& corpus, const Query& q, const SearchResult& r,
                       const SearchOptions& opt, double queryMicros);
