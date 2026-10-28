// text.h - deterministic preprocessing shared by BOTH retrieval architectures.
//
// Rules (applied identically to passages and queries):
//   1. Split on any character that is not an ASCII letter or digit
//      ("CS-251" -> "cs", "251"; punctuation is discarded).
//   2. Lower-case every token.
//   3. Drop stop words (fixed list in text.cpp).
//   4. Light suffix normalisation: "...ies" -> "...y" (len > 4),
//      trailing "s" removed (len > 3, not "ss"/"us"/"is").
// Queries are then turned into concept groups: each distinct query term forms
// one group, optionally widened with synonyms from data/synonyms.txt. Repeated
// query terms collapse into one group, so "fee fee fee" == "fee".
#pragma once

#include <string>
#include <vector>

#include "hash_table.h"

struct QueryGroup {
    std::string original;            // normalised term the user typed
    std::vector<std::string> terms;  // original + synonym expansions (no duplicates)
};

struct Query {
    std::string raw;
    std::vector<QueryGroup> groups;
    bool truncated = false;  // more than kMaxGroups distinct terms were given
    static constexpr size_t kMaxGroups = 64;
};

class TextProcessor {
public:
    TextProcessor();

    // Format: "term: expansion1 expansion2" per line, '#' starts a comment.
    bool loadSynonyms(const std::string& path, std::string& error);
    void setUseSynonyms(bool on) { useSynonyms_ = on; }
    bool useSynonyms() const { return useSynonyms_; }
    size_t synonymCount() const { return synonyms_.size(); }

    std::vector<std::string> tokenize(const std::string& text) const;
    Query parseQuery(const std::string& text) const;

    static std::string normalizeTerm(const std::string& lowerWord);

private:
    HashTable<bool> stopWords_;
    HashTable<std::vector<std::string>> synonyms_;
    bool useSynonyms_ = true;
};
