#include "inverted_index.h"

InvertedIndex::InvertedIndex(size_t initialBuckets, bool allowResize, HashTable<std::vector<Posting>>::HashFn fn)
    : table_(initialBuckets, allowResize, fn) {}

void InvertedIndex::build(const Corpus& corpus) {
    table_.clear();
    for (size_t i = 0; i < corpus.slots(); ++i) {
        const Passage& p = corpus.at(static_cast<int>(i));
        if (!p.deleted) addPassage(static_cast<int>(i), p);
    }
}

void InvertedIndex::addPassage(int index, const Passage& p) {
    for (const std::string& term : p.tokens) {
        std::vector<Posting>& list = table_.getOrInsert(term);
        // Tokens of one passage are processed together, so a repeated term in
        // this passage is always the last posting of its list.
        if (!list.empty() && list.back().passage == index)
            ++list.back().tf;
        else
            list.push_back({index, 1});
    }
}

void InvertedIndex::removePassage(int index, const Passage& p) {
    for (const std::string& term : p.tokens) {
        std::vector<Posting>* list = table_.find(term);
        if (!list) continue;
        for (size_t i = 0; i < list->size(); ++i) {
            if ((*list)[i].passage == index) {
                list->erase(list->begin() + static_cast<long>(i));  // keeps ascending order
                break;
            }
        }
        if (list->empty()) table_.erase(term);
    }
}

IndexMemory InvertedIndex::memory() const {
    IndexMemory m;
    m.bucketArray = table_.bucketArrayBytes();
    m.nodes = table_.nodeBytes();
    m.keyHeap = table_.keyHeapBytes();
    table_.forEach([&](const std::string&, const std::vector<Posting>& list) {
        m.postings += list.capacity() * sizeof(Posting);
        m.postingCount += list.size();
    });
    return m;
}
