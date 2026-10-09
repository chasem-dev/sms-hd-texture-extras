# Texture audit

`scan.py` lists the disc's textures that no installed pack replaces (see the main README).

`fast.c` is an optional C helper that decompresses Yaz0 and hashes XXH64 for both scripts.
Without it everything still works in pure Python, only slower: about two seconds with it, several minutes without.

```sh
gcc -O2 -shared -fPIC -o tools/audit/fast.so tools/audit/fast.c
```
