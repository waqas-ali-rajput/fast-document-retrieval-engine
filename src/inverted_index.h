// inverted_index.h - student-built inverted index.
//
// vocabulary (custom HashTable)  term -> postings array
// postings: contiguous array of {passage index, term frequency}, kept in
// ascending passage order because passages are indexed in arrival order.
//   duplicate term occurrences in one passage -> a single posting with tf > 1
//   new passage   -> its postings are appended (O(tokens of that passage))
//   removed / updated passage -> its postings are removed from every list it
//                    appears in, then the new version is indexed as a new passage
#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "corpus.h"
#include "hash_table.h"

struct Posting {
    int passage;
    int tf;
};

struct IndexMemory {
    size_t bucketArray = 0;
    size_t nodes = 0;
    size_t keyHeap = 0;
    size_t postings = 0;
    size_t postingCount = 0;
    size_t total() const { return bucketArray + nodes + keyHeap + postings; }
};

class InvertedIndex {
public:
    explicit InvertedIndex(size_t initialBuckets = 64, bool allowResize = true,
                           HashTable<std::vector<Posting>>::HashFn fn = fnv1a);

    void build(const Corpus& corpus);
    void addPassage(int index, const Passage& p);
    void removePassage(int index, const Passage& p);

    const std::vector<Posting>* lookup(const std::string& term) const { return table_.find(term); }
    size_t vocabularySize() const { return table_.size(); }
    HashStats hashStats() const { return table_.stats(); }
    IndexMemory memory() const;

private:
    HashTable<std::vector<Posting>> table_;
};
