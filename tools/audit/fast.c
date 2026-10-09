#include <stdint.h>
#include <string.h>
#include <stddef.h>
/* Yaz0: returns decoded size (out must hold it) */
size_t yaz0(const uint8_t* s, size_t n, uint8_t* o, size_t osize) {
    size_t i = 16, p = 0;
    while (p < osize && i < n) {
        uint8_t code = s[i++];
        for (int b = 0; b < 8 && p < osize; b++) {
            if (code & (0x80 >> b)) o[p++] = s[i++];
            else {
                uint8_t b1 = s[i], b2 = s[i + 1]; i += 2;
                size_t dist = (((size_t)(b1 & 15) << 8) | b2) + 1, len = b1 >> 4;
                if (len == 0) len = (size_t)s[i++] + 0x12; else len += 2;
                for (size_t k = 0; k < len && p < osize; k++, p++) o[p] = o[p - dist];
            }
        }
    }
    return p;
}
static const uint64_t P1 = 11400714785074694791ULL, P2 = 14029467366897019727ULL, P3 = 1609587929392839161ULL,
                      P4 = 9650029242287828579ULL, P5 = 2870177450012600261ULL;
static uint64_t rotl(uint64_t x, int r) { return (x << r) | (x >> (64 - r)); }
static uint64_t rd64(const uint8_t* p) { uint64_t v; memcpy(&v, p, 8); return v; }
static uint32_t rd32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }
static uint64_t rnd(uint64_t a, uint64_t i) { a += i * P2; a = rotl(a, 31); return a * P1; }
static uint64_t mrg(uint64_t a, uint64_t v) { a ^= rnd(0, v); return a * P1 + P4; }
uint64_t xxh64(const uint8_t* p, size_t n, uint64_t seed) {
    const uint8_t* e = p + n; uint64_t h;
    if (n >= 32) {
        uint64_t v1 = seed + P1 + P2, v2 = seed + P2, v3 = seed, v4 = seed - P1;
        while (p + 32 <= e) { v1 = rnd(v1, rd64(p)); v2 = rnd(v2, rd64(p + 8)); v3 = rnd(v3, rd64(p + 16)); v4 = rnd(v4, rd64(p + 24)); p += 32; }
        h = rotl(v1, 1) + rotl(v2, 7) + rotl(v3, 12) + rotl(v4, 18);
        h = mrg(h, v1); h = mrg(h, v2); h = mrg(h, v3); h = mrg(h, v4);
    } else h = seed + P5;
    h += n;
    while (p + 8 <= e) { h ^= rnd(0, rd64(p)); h = rotl(h, 27) * P1 + P4; p += 8; }
    if (p + 4 <= e) { h ^= (uint64_t)rd32(p) * P1; h = rotl(h, 23) * P2 + P3; p += 4; }
    while (p < e) { h ^= (*p) * P5; h = rotl(h, 11) * P1; p++; }
    h ^= h >> 33; h *= P2; h ^= h >> 29; h *= P3; h ^= h >> 32;
    return h;
}
