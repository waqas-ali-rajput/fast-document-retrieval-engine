// hash_table.h - student-built separate-chaining hash table (string keys).
//
// Assessed component #1. std::unordered_map is deliberately NOT used anywhere
// in the retrieval logic. Buckets are a plain array (std::vector used only as a
// raw buffer of pointers); every bucket holds a singly linked list of nodes.
//
//   hash:        FNV-1a 64-bit (can be replaced, e.g. to force collisions in tests)
//   collisions:  separate chaining - colliding keys share a bucket's linked list
//   growth:      when entries / buckets would exceed 0.75 the bucket array is
//                doubled and every node is relinked (no node is reallocated)
//   duplicates:  inserting an existing key returns the existing value slot
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

inline uint64_t fnv1a(const std::string& s) {
    uint64_t h = 1469598103934665603ULL;
    for (unsigned char c : s) {
        h ^= c;
        h *= 1099511628211ULL;
    }
    return h;
}

struct HashStats {
    size_t buckets = 0;
    size_t entries = 0;
    size_t usedBuckets = 0;
    size_t maxChain = 0;
    size_t collidingEntries = 0;  // entries that share a bucket with an earlier entry
    size_t resizes = 0;
    double loadFactor = 0.0;
    double avgChainUsed = 0.0;    // average chain length over non-empty buckets
};

template <typename V>
class HashTable {
public:
    using HashFn = uint64_t (*)(const std::string&);

    explicit HashTable(size_t initialBuckets = 16, bool allowResize = true, HashFn fn = fnv1a)
        : buckets_(initialBuckets ? initialBuckets : 1, nullptr), allowResize_(allowResize), hash_(fn) {}

    ~HashTable() { clear(); }

    HashTable(const HashTable&) = delete;
    HashTable& operator=(const HashTable&) = delete;

    V* find(const std::string& key) {
        Node* n = findNode(key);
        return n ? &n->value : nullptr;
    }

    const V* find(const std::string& key) const {
        const Node* n = findNode(key);
        return n ? &n->value : nullptr;
    }

    bool contains(const std::string& key) const { return findNode(key) != nullptr; }

    // Returns the value slot for key, creating a default-constructed value if absent.
    V& getOrInsert(const std::string& key, bool* inserted = nullptr) {
        size_t b = bucketOf(key);
        for (Node* n = buckets_[b]; n; n = n->next) {
            if (n->key == key) {
                if (inserted) *inserted = false;
                return n->value;
            }
        }
        if (allowResize_ && static_cast<double>(size_ + 1) > kMaxLoad * static_cast<double>(buckets_.size())) {
            rehash(buckets_.size() * 2);
            b = bucketOf(key);
        }
        Node* n = new Node{key, V{}, buckets_[b]};
        buckets_[b] = n;
        ++size_;
        if (inserted) *inserted = true;
        return n->value;
    }

    void put(const std::string& key, const V& value) { getOrInsert(key) = value; }

    bool erase(const std::string& key) {
        size_t b = bucketOf(key);
        Node* prev = nullptr;
        for (Node* n = buckets_[b]; n; prev = n, n = n->next) {
            if (n->key == key) {
                (prev ? prev->next : buckets_[b]) = n->next;
                delete n;
                --size_;
                return true;
            }
        }
        return false;
    }

    void clear() {
        for (Node*& head : buckets_) {
            while (head) {
                Node* next = head->next;
                delete head;
                head = next;
            }
        }
        size_ = 0;
    }

    size_t size() const { return size_; }
    size_t bucketCount() const { return buckets_.size(); }

    template <typename F>
    void forEach(F f) const {
        for (const Node* head : buckets_)
            for (const Node* n = head; n; n = n->next) f(n->key, n->value);
    }

    HashStats stats() const {
        HashStats s;
        s.buckets = buckets_.size();
        s.entries = size_;
        s.resizes = resizes_;
        for (const Node* head : buckets_) {
            size_t len = 0;
            for (const Node* n = head; n; n = n->next) ++len;
            if (len) {
                ++s.usedBuckets;
                s.collidingEntries += len - 1;
                if (len > s.maxChain) s.maxChain = len;
            }
        }
        s.loadFactor = s.buckets ? static_cast<double>(s.entries) / static_cast<double>(s.buckets) : 0.0;
        s.avgChainUsed = s.usedBuckets ? static_cast<double>(s.entries) / static_cast<double>(s.usedBuckets) : 0.0;
        return s;
    }

    // Approximate bytes owned by the table structure itself (bucket array, nodes,
    // heap storage of long keys). Value-owned heap memory is accounted by callers.
    size_t bucketArrayBytes() const { return buckets_.capacity() * sizeof(Node*); }
    size_t nodeBytes() const { return size_ * sizeof(Node); }
    size_t keyHeapBytes() const {
        size_t bytes = 0;
        forEach([&](const std::string& k, const V&) {
            if (k.capacity() > kSsoCapacity) bytes += k.capacity() + 1;
        });
        return bytes;
    }

private:
    struct Node {
        std::string key;
        V value;
        Node* next;
    };

    static constexpr double kMaxLoad = 0.75;
    static constexpr size_t kSsoCapacity = 15;  // libstdc++ short-string buffer

    std::vector<Node*> buckets_;
    size_t size_ = 0;
    size_t resizes_ = 0;
    bool allowResize_;
    HashFn hash_;

    size_t bucketOf(const std::string& key) const { return static_cast<size_t>(hash_(key) % buckets_.size()); }

    Node* findNode(const std::string& key) const {
        for (Node* n = buckets_[bucketOf(key)]; n; n = n->next)
            if (n->key == key) return n;
        return nullptr;
    }

    void rehash(size_t newCount) {
        std::vector<Node*> fresh(newCount, nullptr);
        for (Node* head : buckets_) {
            while (head) {
                Node* next = head->next;
                size_t b = static_cast<size_t>(hash_(head->key) % newCount);
                head->next = fresh[b];
                fresh[b] = head;
                head = next;
            }
        }
        buckets_.swap(fresh);
        ++resizes_;
    }
};
