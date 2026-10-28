// top_k_heap.h - student-built bounded binary heap for top-k selection.
//
// Assessed component #2. std::priority_queue is NOT used.
// The heap keeps at most k elements and its root is always the WORST element
// kept so far, so a new candidate is compared against the root in O(1) and
// replaces it in O(log k). Selecting k results from C candidates therefore
// costs O(C log k) time and O(k) extra space, versus O(C log C) for sorting
// every candidate.
#pragma once

#include <cstddef>
#include <utility>
#include <vector>

template <typename T, typename Better>
class TopKHeap {
public:
    TopKHeap(size_t k, Better better) : k_(k), better_(better) { data_.reserve(k); }

    void offer(const T& x) {
        if (k_ == 0) return;
        if (data_.size() < k_) {
            data_.push_back(x);
            siftUp(data_.size() - 1);
        } else if (better_(x, data_[0])) {
            data_[0] = x;
            siftDown(0);
        }
    }

    size_t size() const { return data_.size(); }

    // Empties the heap and returns the kept elements ordered best first.
    std::vector<T> takeBestFirst() {
        std::vector<T> out(data_.size());
        for (size_t i = out.size(); i-- > 0;) {
            out[i] = data_[0];  // current worst goes to the back
            data_[0] = data_.back();
            data_.pop_back();
            if (!data_.empty()) siftDown(0);
        }
        return out;
    }

private:
    size_t k_;
    Better better_;
    std::vector<T> data_;  // array-backed complete binary tree

    bool worse(const T& a, const T& b) const { return better_(b, a); }

    void siftUp(size_t i) {
        while (i > 0) {
            size_t parent = (i - 1) / 2;
            if (!worse(data_[i], data_[parent])) break;
            std::swap(data_[i], data_[parent]);
            i = parent;
        }
    }

    void siftDown(size_t i) {
        const size_t n = data_.size();
        for (;;) {
            size_t l = 2 * i + 1, r = l + 1, m = i;
            if (l < n && worse(data_[l], data_[m])) m = l;
            if (r < n && worse(data_[r], data_[m])) m = r;
            if (m == i) return;
            std::swap(data_[i], data_[m]);
            i = m;
        }
    }
};
