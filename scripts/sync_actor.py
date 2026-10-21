"""Vendor the Python packages into actor/ so the Apify actor directory is self-contained
(Apify builds with actor/ as the Docker context). Run after changing library code; tests check it's in sync."""
import pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKGS = ["biocatalystfeed", "biowatch", "trialwatch", "fdawatch", "grantwatch", "paperwatch", "secwatch", "emawatch", "adcomwatch"]
DEST = ROOT / "actor" / "src"


def files(base: pathlib.Path):
    return {p.relative_to(base): p.read_bytes() for pkg in PKGS for p in (base / pkg).rglob("*.py")}


def main(check: bool = False) -> int:
    want, have = files(ROOT), (files(DEST) if DEST.exists() else {})
    if check:
        return 0 if want == have else 1
    shutil.rmtree(DEST, ignore_errors=True)
    for rel, data in want.items():
        (DEST / rel).parent.mkdir(parents=True, exist_ok=True); (DEST / rel).write_bytes(data)
    print(f"vendored {len(want)} files into {DEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
