#!/usr/bin/env python3
from pathlib import Path
import sys, unicodedata
import polib

ENC = {
    **{lg: "CP1250" for lg in ("cs", "hu", "pl", "sk")},
    **{lg: "CP1251" for lg in ("be", "bg", "ru", "uk")},
    **{lg: "CP1252" for lg in ("de", "dk", "es", "fr", "it", "nb", "pt", "sv", "nl")},
    "gr": "CP1253",
    "tr": "CP1254",
    "lt": "CP1257",
    "vi": "CP1258",
    "ro": "ISO-8859-16",
}
TRANSLIT = str.maketrans("äëïöőüűÄËÏŐÖÜŰ", "aeioouuAEIOOUU")


def ascii_t(text: str) -> str:
    txt = text.translate(TRANSLIT)
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore")
    return txt.decode("ascii")


def safe_kodolas(text: str, enc: str) -> str:
    try:
        text.encode(enc)
        return text
    except UnicodeEncodeError:
        no_diacrit = unicodedata.normalize("NFKD", text)
        no_diacrit = "".join(c for c in no_diacrit if not unicodedata.combining(c))
        return no_diacrit.encode(enc, "ignore").decode(enc)


def compile_one(po_path: Path):
    lang, encoding = po_path.stem.lower(), ENC.get(po_path.stem.lower(), "ASCII")
    po = polib.pofile(po_path)
    po.encoding = po.charset = encoding
    po.metadata["Content-Type"] = f"text/plain; charset={encoding}"
    po.metadata["Content-Transfer-Encoding"] = "8bit"

    if encoding == "ASCII":
        for e in po:
            e.msgstr = ascii_t(e.msgstr)
            for k in e.msgstr_plural:
                e.msgstr_plural[k] = ascii_t(e.msgstr_plural[k])
    else:
        for e in po:
            e.msgstr = safe_kodolas(e.msgstr, encoding)
            for k in e.msgstr_plural:
                e.msgstr_plural[k] = safe_kodolas(e.msgstr_plural[k], encoding)

    po.save_as_mofile(po_path.with_suffix(".mo"))
    print(f"✓ {po_path.name} → {po_path.stem}.mo  ({encoding})")


def main(argv):
    for mo in Path(".").rglob("*.mo"):
        mo.unlink(missing_ok=True)
    targets = [Path(p) for p in argv] if argv else Path(".").rglob("*.po")
    for po in targets:
        compile_one(po)


if __name__ == "__main__":
    main(sys.argv[1:])
