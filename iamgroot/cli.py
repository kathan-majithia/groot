"""
cli.py
======
Usage:
    python -m iamgroot encode "some text" out.wav [password]
    python -m iamgroot decode out.wav [password]
"""
import sys

from .encoder import encode
from .decoder import decode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "encode":
        if len(sys.argv) not in (4, 5):
            print("Usage: python -m iamgroot encode \"text\" out.wav [password]")
            sys.exit(1)
        text, out_path = sys.argv[2], sys.argv[3]
        password = sys.argv[4] if len(sys.argv) == 5 else None
        encode(text, out_path, password=password)
        print(f"Encoded -> {out_path}" + (" (password-protected)" if password else ""))
    elif cmd == "decode":
        if len(sys.argv) not in (3, 4):
            print("Usage: python -m iamgroot decode out.wav [password]")
            sys.exit(1)
        wav_path = sys.argv[2]
        password = sys.argv[3] if len(sys.argv) == 4 else None
        text = decode(wav_path, password=password)
        print(f"Decoded text: {text}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
