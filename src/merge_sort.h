// merge_sort.h - student-built stable merge sort.
//
// Assessed component #3 (alternative top-k policy): sort ALL candidates in
// O(C log C) time with O(C) auxiliary space, then keep the first k. Used to
// compare against the bounded heap in top_k_heap.h.
#pragma once

#include <cstddef>
#include <vector>

namespace detail {
template <typename T, typename Less>
void mergeSortRange(std::vector<T>& a, std::vector<T>& tmp, size_t lo, size_t hi, Less& less) {
    if (hi - lo < 2) return;
    size_t mid = lo + (hi - lo) / 2;
    mergeSortRange(a, tmp, lo, mid, less);
    mergeSortRange(a, tmp, mid, hi, less);
    size_t i = lo, j = mid, k = lo;
    while (i < mid && j < hi) tmp[k++] = less(a[j], a[i]) ? a[j++] : a[i++];  // ties keep left: stable
    while (i < mid) tmp[k++] = a[i++];
    while (j < hi) tmp[k++] = a[j++];
    for (size_t x = lo; x < hi; ++x) a[x] = tmp[x];
}
}  // namespace detail

template <typename T, typename Less>
void mergeSort(std::vector<T>& a, Less less) {
    std::vector<T> tmp(a.size());
    detail::mergeSortRange(a, tmp, 0, a.size(), less);
}
