#include "text.h"

#include <fstream>

namespace {
const char* const kStopWords[] = {
    "a",     "an",    "the",   "is",    "are",   "am",   "was",   "were",  "be",    "been",  "to",
    "of",    "in",    "on",    "at",    "by",    "for",  "from",  "with",  "and",   "or",    "not",
    "no",    "i",     "me",    "my",    "we",    "you",  "your",  "it",    "its",   "this",  "that",
    "these", "those", "as",    "if",    "can",   "could", "do",   "does",  "did",   "what",  "when",
    "where", "which", "who",   "how",   "why",   "will", "would", "should", "must", "may",   "there",
    "their", "they",  "them",  "he",    "she",   "his",  "her",   "all",   "any",   "each",  "after",
    "before", "about", "into", "than",  "then",  "so",   "such",  "only",  "also",  "up",    "per",
    "other",
};

bool isWordChar(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

char toLower(char c) { return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c; }

bool endsWith(const std::string& s, const char* suffix) {
    size_t n = std::char_traits<char>::length(suffix);
    return s.size() >= n && s.compare(s.size() - n, n, suffix) == 0;
}

std::string trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

void pushUnique(std::vector<std::string>& v, const std::string& x) {
    for (const auto& y : v)
        if (y == x) return;
    v.push_back(x);
}
}  // namespace

TextProcessor::TextProcessor() : stopWords_(128), synonyms_(64) {
    for (const char* w : kStopWords) stopWords_.put(w, true);
}

std::string TextProcessor::normalizeTerm(const std::string& w) {
    if (w.size() > 4 && endsWith(w, "ies")) return w.substr(0, w.size() - 3) + "y";
    if (w.size() > 3 && w.back() == 's' && !endsWith(w, "ss") && !endsWith(w, "us") && !endsWith(w, "is"))
        return w.substr(0, w.size() - 1);
    return w;
}

std::vector<std::string> TextProcessor::tokenize(const std::string& text) const {
    std::vector<std::string> out;
    std::string cur;
    auto flush = [&]() {
        if (!cur.empty() && !stopWords_.contains(cur)) out.push_back(normalizeTerm(cur));
        cur.clear();
    };
    for (char c : text) {
        if (isWordChar(c))
            cur.push_back(toLower(c));
        else
            flush();
    }
    flush();
    return out;
}

bool TextProcessor::loadSynonyms(const std::string& path, std::string& error) {
    std::ifstream in(path);
    if (!in) {
        error = "cannot open synonyms file: " + path;
        return false;
    }
    std::string line;
    while (std::getline(in, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        size_t colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::vector<std::string> head = tokenize(line.substr(0, colon));
        if (head.size() != 1) continue;
        std::vector<std::string>& list = synonyms_.getOrInsert(head[0]);
        for (const auto& t : tokenize(line.substr(colon + 1))) pushUnique(list, t);
    }
    return true;
}

Query TextProcessor::parseQuery(const std::string& text) const {
    Query q;
    q.raw = text;
    for (const std::string& t : tokenize(text)) {
        bool seen = false;
        for (const auto& g : q.groups)
            if (g.original == t) seen = true;
        if (seen) continue;  // repeated query term -> same concept
        if (q.groups.size() == Query::kMaxGroups) {
            q.truncated = true;
            break;
        }
        QueryGroup g;
        g.original = t;
        g.terms.push_back(t);
        if (useSynonyms_) {
            if (const auto* syn = synonyms_.find(t))
                for (const auto& s : *syn) pushUnique(g.terms, s);
        }
        q.groups.push_back(g);
    }
    return q;
}
