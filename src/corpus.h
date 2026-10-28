// corpus.h - passage store with provenance metadata.
//
// Passages live in a contiguous array (std::vector<Passage>); the array index
// is the internal passage reference stored in postings. Two student-built hash
// tables sit on top of it:
//   idIndex_   passage_id      -> array index (unique-ID check, updates)
//   textIndex_ normalised text -> first array index with that text
//                               (exact / normalised duplicate detection)
#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "hash_table.h"
#include "text.h"

struct Passage {
    std::string id;        // passage_id, e.g. D09-P1
    std::string docId;     // document_id, e.g. D09
    std::string title;     // document title
    std::string category;  // course | lab | exam | notice | admissions
    std::string version;   // source version label
    std::string date;      // ISO date of the source document (YYYY-MM-DD)
    std::string status;    // "current" or "superseded"
    std::string text;
    std::vector<std::string> tokens;  // preprocessed once at ingestion
    int canonical = -1;  // index of the first passage with identical normalised text
    bool deleted = false;

    bool superseded() const { return status == "superseded"; }
};

class Corpus {
public:
    Corpus();
    Corpus(const Corpus&) = delete;
    Corpus& operator=(const Corpus&) = delete;

    // File format: '|' separated, one passage per line, '#' comment lines:
    // passage_id|document_id|title|category|version|date|status|text
    bool load(const std::string& path, const TextProcessor& tp, std::string& error,
              size_t limit = static_cast<size_t>(-1));

    // Returns the new array index, or -1 if the id already exists.
    int add(Passage p, const TextProcessor& tp);
    // Marks a passage deleted (the slot is kept so other indices stay valid).
    bool remove(int index);

    int findById(const std::string& id) const;
    const Passage& at(int index) const { return passages_[static_cast<size_t>(index)]; }
    size_t slots() const { return passages_.size(); }
    size_t liveCount() const { return live_; }
    size_t totalTokens() const { return totalTokens_; }
    double avgLength() const { return live_ ? static_cast<double>(totalTokens_) / static_cast<double>(live_) : 0.0; }
    bool isDuplicateOfOther(int index) const;

    size_t documentTextBytes() const;  // raw text + metadata strings
    size_t tokenStorageBytes() const;  // preprocessed token arrays

private:
    std::vector<Passage> passages_;
    HashTable<int> idIndex_;
    HashTable<int> textIndex_;
    size_t live_ = 0;
    size_t totalTokens_ = 0;

    static std::string normalisedKey(const Passage& p);
};
