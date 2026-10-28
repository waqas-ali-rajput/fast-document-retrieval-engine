CXX ?= g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra
SRC = src/main.cpp src/text.cpp src/corpus.cpp src/inverted_index.cpp src/retriever.cpp src/evaluation.cpp src/tests.cpp

rag: $(SRC) src/*.h
	$(CXX) $(CXXFLAGS) -o rag $(SRC)

test: rag
	./rag test

eval: rag
	./rag eval

clean:
	rm -f rag rag.exe

.PHONY: test eval clean
