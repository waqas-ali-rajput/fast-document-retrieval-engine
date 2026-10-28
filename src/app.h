// app.h - shared configuration for the command-line program.
#pragma once

#include <iosfwd>
#include <string>
#include <vector>

struct Paths {
    std::string passages = "data/passages.txt";
    std::string queries = "data/queries.txt";
    std::string synonyms = "data/synonyms.txt";
    std::string results = "results";
};

struct LabelledQuery {
    std::string id;
    std::string type;
    std::string text;
    std::vector<std::string> gold;  // empty for unanswerable questions
    std::string note;
};

bool loadQueries(const std::string& path, std::vector<LabelledQuery>& out, std::string& error);

int runEvaluation(const Paths& paths, std::ostream& out);  // evaluation mode
int runTests(const Paths& paths, std::ostream& out);       // edge-case test suite
