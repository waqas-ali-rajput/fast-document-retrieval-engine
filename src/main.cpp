// main.cpp - one integrated program: ingestion -> indexing -> query processing
// -> ranking -> evidence output, plus evaluation and test modes.
//
//   rag query "<question>" [options]   one search, prints the evidence package
//   rag interactive [options]          type questions, blank line to quit
//   rag eval                           full evaluation (results/ folder)
//   rag test                           edge-case test suite
//   rag stats                          corpus, index, hash table and memory figures
// Options: --k N  --mode index|scan  --ranker bm25f|coverage  --topk heap|sort
//          --min-coverage X  --no-synonyms  --data FILE  --json  --time-runs N
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>

#include "app.h"
#include "corpus.h"
#include "inverted_index.h"
#include "retriever.h"
#include "text.h"

namespace {
void usage() {
    std::cout << "Fast Document Retrieval Engine (CS-251 PBL)\n\n"
                 "Usage:\n"
                 "  rag query \"<question>\" [options]\n"
                 "  rag interactive [options]\n"
                 "  rag eval\n"
                 "  rag test\n"
                 "  rag stats\n\n"
                 "Options:\n"
                 "  --k N                 number of passages to return (default 3)\n"
                 "  --mode index|scan     inverted index (default) or linear-scan baseline\n"
                 "  --ranker bm25f|coverage  BM25 + freshness (default) or concept coverage\n"
                 "  --topk heap|sort      bounded heap (default) or merge sort of all candidates\n"
                 "  --min-coverage X      evidence rule, fraction of query concepts (default 0.5)\n"
                 "  --no-synonyms         disable query expansion\n"
                 "  --data FILE           passages file (default data/passages.txt)\n";
}

struct Cli {
    std::string command;
    std::string question;
    SearchOptions opt;
    bool synonyms = true;
    bool json = false;
    int timeRuns = 1;
    Paths paths;
};

bool parse(int argc, char** argv, Cli& cli) {
    if (argc < 2) return false;
    cli.command = argv[1];
    int i = 2;
    if (cli.command == "query") {
        if (argc < 3) return false;
        cli.question = argv[2];
        i = 3;
    }
    for (; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
        if (a == "--k") {
            cli.opt.k = static_cast<size_t>(std::strtoul(next().c_str(), nullptr, 10));
        } else if (a == "--mode") {
            std::string v = next();
            if (v != "index" && v != "scan") return false;
            cli.opt.mode = v == "scan" ? Mode::Scan : Mode::Index;
        } else if (a == "--ranker") {
            std::string v = next();
            if (v != "bm25f" && v != "coverage") return false;
            cli.opt.ranker = v == "coverage" ? Ranker::Coverage : Ranker::Bm25Fresh;
        } else if (a == "--topk") {
            std::string v = next();
            if (v != "heap" && v != "sort") return false;
            cli.opt.topk = v == "sort" ? TopKMethod::MergeSort : TopKMethod::Heap;
        } else if (a == "--min-coverage") {
            cli.opt.minCoverage = std::strtod(next().c_str(), nullptr);
        } else if (a == "--no-synonyms") {
            cli.synonyms = false;
        } else if (a == "--json") {
            cli.json = true;
        } else if (a == "--time-runs") {
            cli.timeRuns = std::max(1, std::atoi(next().c_str()));
        } else if (a == "--data") {
            cli.paths.passages = next();
        } else {
            std::cerr << "Unknown option: " << a << '\n';
            return false;
        }
    }
    return true;
}

void runSearch(const Retriever& r, const Corpus& c, const TextProcessor& tp, const std::string& question,
               const Cli& cli) {
    Query q = tp.parseQuery(question);
    SearchResult res;
    std::vector<double> times;  // median of --time-runs searches
    for (int i = 0; i < cli.timeRuns; ++i) {
        auto t0 = std::chrono::steady_clock::now();
        res = r.search(q, cli.opt);
        auto t1 = std::chrono::steady_clock::now();
        times.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count());
    }
    std::sort(times.begin(), times.end());
    const double micros = times[times.size() / 2];
    if (cli.json) {
        printEvidenceJson(std::cout, c, q, res, cli.opt, micros);
        return;
    }
    printEvidence(std::cout, c, q, res, cli.opt);
    std::cout << "Query time: " << std::fixed << std::setprecision(1) << micros << " us ("
              << (cli.timeRuns > 1 ? "median of " + std::to_string(cli.timeRuns) + " runs" : "single run")
              << "; use 'rag eval' for full benchmarks)\n";
    std::cout.unsetf(std::ios::floatfield);
}
}  // namespace

int main(int argc, char** argv) {
    Cli cli;
    if (!parse(argc, argv, cli)) {
        usage();
        return 1;
    }
    if (cli.command == "eval") return runEvaluation(cli.paths, std::cout);
    if (cli.command == "test") return runTests(cli.paths, std::cout);
    if (cli.command != "query" && cli.command != "interactive" && cli.command != "stats") {
        usage();
        return 1;
    }

    std::string err;
    TextProcessor tp;
    tp.setUseSynonyms(cli.synonyms);
    if (!tp.loadSynonyms(cli.paths.synonyms, err)) std::cerr << "Warning: " << err << '\n';

    Corpus corpus;
    auto t0 = std::chrono::steady_clock::now();
    if (!corpus.load(cli.paths.passages, tp, err)) {
        std::cerr << "Error: " << err << '\n';
        return 1;
    }
    auto t1 = std::chrono::steady_clock::now();
    InvertedIndex index;
    index.build(corpus);
    auto t2 = std::chrono::steady_clock::now();
    Retriever retriever(corpus, index);

    if (cli.command == "stats") {
        const IndexMemory m = index.memory();
        const HashStats h = index.hashStats();
        std::cout << std::fixed << std::setprecision(3);
        std::cout << "Passages (N)         : " << corpus.liveCount() << '\n'
                  << "Tokens (T)           : " << corpus.totalTokens() << "  (avg " << corpus.avgLength()
                  << " per passage)\n"
                  << "Unique terms (V)     : " << index.vocabularySize() << '\n'
                  << "Postings             : " << m.postingCount << '\n'
                  << "Load + preprocess    : " << std::chrono::duration<double, std::milli>(t1 - t0).count() << " ms\n"
                  << "Index build          : " << std::chrono::duration<double, std::milli>(t2 - t1).count() << " ms\n"
                  << "Hash buckets         : " << h.buckets << " (load factor " << h.loadFactor << ", "
                  << h.resizes << " resizes)\n"
                  << "Longest chain        : " << h.maxChain << ", colliding entries " << h.collidingEntries
                  << ", avg chain (used buckets) " << h.avgChainUsed << '\n'
                  << "Index memory (bytes) : buckets " << m.bucketArray << " + nodes " << m.nodes << " + long keys "
                  << m.keyHeap << " + postings " << m.postings << " = " << m.total() << '\n'
                  << "Document storage     : text+metadata " << corpus.documentTextBytes() << " B, token arrays "
                  << corpus.tokenStorageBytes() << " B (not counted as index)\n"
                  << "Synonym entries      : " << tp.synonymCount() << '\n';
        return 0;
    }

    if (cli.command == "query") {
        runSearch(retriever, corpus, tp, cli.question, cli);
        return 0;
    }

    std::cout << "Loaded " << corpus.liveCount() << " passages, " << index.vocabularySize()
              << " terms. Type a question (blank line to quit).\n";
    std::string line;
    while (std::cout << "\n> " && std::getline(std::cin, line) && !line.empty()) {
        std::cout << '\n';
        runSearch(retriever, corpus, tp, line, cli);
    }
    return 0;
}
