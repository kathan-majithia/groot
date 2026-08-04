"""
selftest.py
===========
Quick built-in sanity check: encode a sample sentence, decode it back,
assert equality, print pass/fail. Run with:

    python3 -m iamgroot.selftest
"""
from .encoder import encode
from .decoder import decode


def run():
    samples = [
        "Hello, My name is Kathan Majithia pursuing Engineering in Gujarat",
        "I am Groot.",
        "42",
    ]
    all_ok = True
    for i, text in enumerate(samples):
        path = f"/tmp/iamgroot_selftest_{i}.wav"
        encode(text, path)
        out = decode(path)
        ok = out == text
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {text!r} -> {out!r}")
    print("SELF-TEST:", "ALL PASSED" if all_ok else "FAILED")
    return all_ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
