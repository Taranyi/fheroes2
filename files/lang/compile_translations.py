#!/usr/bin/env python3
"""Compile .po translation files into .mo files.

This script replicates the logic of the original Makefile but in Python so it
can run on platforms where `make` is not available.

Usage:
    python3 compile_translations.py [po-files ...]

When run without arguments, all .po files in the current directory are
processed. When arguments are passed, they specify which .po files to compile.
A `clean` argument removes compiled .mo files.
"""
import subprocess
import unicodedata
from pathlib import Path
import sys

ENCODINGS = {
    "cs": "CP1250",
    "hu": "CP1250",
    "pl": "CP1250",
    "sk": "CP1250",
    "be": "CP1251",
    "bg": "CP1251",
    "ru": "CP1251",
    "uk": "CP1251",
    "de": "CP1252",
    "dk": "CP1252",
    "es": "CP1252",
    "fr": "CP1252",
    "it": "CP1252",
    "nb": "CP1252",
    "pt": "CP1252",
    "sv": "CP1252",
    "nl": "CP1252",
    "gr": "CP1253",
    "tr": "CP1254",
    "lt": "CP1257",
    "vi": "CP1258",
    "ro": "ISO-8859-16",
}

TRANSLIT_MAP = str.maketrans("äëïöőüűÄËÏŐÖÜŰ", "aeioouuAEIOOUU")


def msgfmt_supports_no_convert() -> bool:
    try:
        help_text = subprocess.check_output(["msgfmt", "--help"], text=True)
        return "--no-convert" in help_text
    except Exception:
        return False


def compile_file(po_path: Path, mo_path: Path, encoding: str, use_no_convert: bool):
    with po_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    for i in range(min(20, len(lines))):
        lines[i] = lines[i].replace("UTF-8", encoding)
    data = "".join(lines)
    if encoding == "ascii":
        data = data.translate(TRANSLIT_MAP)
        data = unicodedata.normalize("NFKD", data).encode("ascii", "ignore")
    else:
        data = data.encode(encoding, errors="ignore")
    cmd = ["msgfmt", "-", "-o", str(mo_path)]
    if use_no_convert:
        cmd.append("--no-convert")
    subprocess.run(cmd, input=data, check=True)


def main(argv):
    if len(argv) > 1 and argv[1] == "clean":
        for mo in Path.cwd().glob("*.mo"):
            mo.unlink(missing_ok=True)
        return 0
    use_no_convert = msgfmt_supports_no_convert()
    if len(argv) > 1:
        po_files = [Path(p) for p in argv[1:]]
    else:
        po_files = list(Path.cwd().glob("*.po"))
    for po in po_files:
        encoding = ENCODINGS.get(po.stem, "ascii")
        mo = po.with_suffix(".mo")
        compile_file(po, mo, encoding, use_no_convert)
        print(f"Compiled {po} -> {mo} ({encoding})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
