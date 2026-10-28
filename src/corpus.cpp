#include "corpus.h"

#include <fstream>

namespace {
std::vector<std::string> splitPipe(const std::string& line) {
    std::vector<std::string> parts;
    std::string cur;
    for (char c : line) {
        if (c == '|') {
            parts.push_back(cur);
            cur.clear();
        } else if (c != '\r') {
            cur.push_back(c);
        }
    }
    parts.push_back(cur);
    return parts;
}

size_t stringBytes(const std::string& s) { return sizeof(std::string) + (s.capacity() > 15 ? s.capacity() + 1 : 0); }
}  // namespace

Corpus::Corpus() : idIndex_(256), textIndex_(256) {}

std::string Corpus::normalisedKey(const Passage& p) {
    std::string key;
    for (const auto& t : p.tokens) {
        key += t;
        key += ' ';
    }
    return key;
}

bool Corpus::load(const std::string& path, const TextProcessor& tp, std::string& error, size_t limit) {
    std::ifstream in(path);
    if (!in) {
        error = "cannot open corpus file: " + path;
        return false;
    }
    std::string line;
    size_t lineNo = 0;
    while (live_ < limit && std::getline(in, line)) {
        ++lineNo;
        if (line.empty() || line[0] == '#' || line == "\r") continue;
        std::vector<std::string> f = splitPipe(line);
        if (f.size() != 8) {
            error = path + ":" + std::to_string(lineNo) + ": expected 8 '|' separated fields";
            return false;
        }
        Passage p{f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], {}, -1, false};
        if (add(std::move(p), tp) < 0) {
            error = path + ":" + std::to_string(lineNo) + ": duplicate passage_id " + f[0];
            return false;
        }
    }
    return true;
}

int Corpus::add(Passage p, const TextProcessor& tp) {
    if (idIndex_.contains(p.id)) return -1;
    p.tokens = tp.tokenize(p.text);
    p.deleted = false;
    const int index = static_cast<int>(passages_.size());

    std::string key = normalisedKey(p);
    bool inserted = false;
    int& first = textIndex_.getOrInsert(key, &inserted);
    if (inserted || passages_[static_cast<size_t>(first)].deleted) first = index;
    p.canonical = first;

    idIndex_.put(p.id, index);
    ++live_;
    totalTokens_ += p.tokens.size();
    passages_.push_back(std::move(p));
    return index;
}

bool Corpus::remove(int index) {
    if (index < 0 || static_cast<size_t>(index) >= passages_.size()) return false;
    Passage& p = passages_[static_cast<size_t>(index)];
    if (p.deleted) return false;
    p.deleted = true;
    --live_;
    totalTokens_ -= p.tokens.size();
    idIndex_.erase(p.id);
    std::string key = normalisedKey(p);
    if (const int* first = textIndex_.find(key); first && *first == index) textIndex_.erase(key);
    return true;
}

int Corpus::findById(const std::string& id) const {
    const int* idx = idIndex_.find(id);
    return idx ? *idx : -1;
}

bool Corpus::isDuplicateOfOther(int index) const {
    const Passage& p = at(index);
    return p.canonical >= 0 && p.canonical != index && !at(p.canonical).deleted;
}

size_t Corpus::documentTextBytes() const {
    size_t bytes = passages_.capacity() * sizeof(Passage);
    for (const auto& p : passages_)
        bytes += stringBytes(p.id) + stringBytes(p.docId) + stringBytes(p.title) + stringBytes(p.category) +
                 stringBytes(p.version) + stringBytes(p.date) + stringBytes(p.status) + stringBytes(p.text) -
                 8 * sizeof(std::string);  // the string headers are already inside sizeof(Passage)
    return bytes;
}

size_t Corpus::tokenStorageBytes() const {
    size_t bytes = 0;
    for (const auto& p : passages_) {
        bytes += p.tokens.capacity() * sizeof(std::string);
        for (const auto& t : p.tokens) bytes += t.capacity() > 15 ? t.capacity() + 1 : 0;
    }
    return bytes;
}
