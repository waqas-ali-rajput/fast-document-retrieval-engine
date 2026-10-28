@echo off
REM Build the retrieval engine with any C++17 compiler (tested with g++ 10.3, TDM-GCC).
g++ -std=c++17 -O2 -Wall -Wextra -o rag.exe src\main.cpp src\text.cpp src\corpus.cpp src\inverted_index.cpp src\retriever.cpp src\evaluation.cpp src\tests.cpp
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)
echo Built rag.exe
