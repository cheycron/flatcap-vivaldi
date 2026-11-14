#!/usr/bin/env python3
"""Prove that each detector of `scripts/build.py --check` (and the exit code of --sync) fails on a matching mutation.

    python3 scripts/mutation_test.py              # mutate a copy of the working tree (tracked and untracked, not ignored files)
    python3 scripts/mutation_test.py --ref HEAD   # mutate a copy made with `git archive HEAD`

Every case copies the repository into a fresh temporary folder, applies ONE mutation there, runs the check and expects a non-zero exit
whose output mentions the expected text. The first case is the unmutated copy and must pass. The repository itself is never modified.
Prints a table and exits 1 if any detector did not fire. Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = "#browser:is(.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001,.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200002)"
# the private strings are assembled here so that this file does not trip the privacy scan itself
WIN_PATH = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "file"
HOME_PATH = "/ho" + "me/someone/file"
IP10, IP172, IP192 = "10." + "1.2.3", "172." + "20.4.5", "192." + "168.1.20"
HOST = "nas" + "." + "lan"


def copy_tree(dst: Path, ref: str | None) -> None:
    if ref:
        data = subprocess.run(["git", "archive", ref], cwd=ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dst)], input=data, check=True)
        return
    names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode().split("\0")
    for n in filter(None, names):
        if (ROOT / n).is_file():
            (dst / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / n, dst / n)


def edit(path: str, fn):
    def run(d: Path):
        f = d / path
        old = f.read_text(encoding="utf-8")
        new = fn(old)
        assert new != old, f"mutation did not change {path}"
        f.write_text(new, encoding="utf-8")
    return run


def sub(old: str, new: str):
    return lambda s: (s.replace(old, new, 1) if old in s else (_ for _ in ()).throw(AssertionError(f"{old!r} not found")))


def append(text: str):
    return lambda s: s + text


def rezip(name: str, **kw):
    """Rewrite themes/<name> keeping settings.json but changing member metadata."""
    def run(d: Path):
        f = d / "themes" / name
        with zipfile.ZipFile(f) as z:
            raw = z.read("settings.json")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            info = zipfile.ZipInfo(kw.get("member", "settings.json"), date_time=kw.get("date", (2026, 1, 1, 0, 0, 0)))
            info.compress_type = kw.get("compress", zipfile.ZIP_DEFLATED)
            info.create_system = 3
            info.external_attr = kw.get("attr", 0o644 << 16)
            z.writestr(info, raw)
            if kw.get("extra_member"):
                z.writestr(zipfile.ZipInfo("notes.txt", date_time=(2026, 1, 1, 0, 0, 0)), b"x")
        f.write_bytes(buf.getvalue())
    return run


def trailing(name: str):
    def run(d: Path):
        f = d / "themes" / name
        f.write_bytes(f.read_bytes() + b"\0" * 16)
    return run


# (id, detector, mutation, command, expected text in the output)
CASES = [
    ("baseline", "unmutated copy passes", None, "--check", None),
    ("scope-1", "rule without theme-id scope", edit("css/flatcap-audio-quiet.css", append("\n.tab-audio { opacity: 1; }\n")), "--check", "without a Flatcap theme-id scope"),
    ("scope-2", "rule scoped to #browser only", edit("css/flatcap-tabs-minimal.css", append("\n@media (forced-colors: none) {\n#browser .tab { opacity: 1; }\n}\n")), "--check", "without a Flatcap theme-id scope"),
    ("layout-1", "transition-property on a layout property", edit("css/flatcap-motion.css", sub("transition-property: background-color;", "transition-property: width;")), "--check", "transitions the layout property width"),
    ("layout-2", "transition shorthand on padding", edit("css/flatcap-surfaces-motion.css", sub("transition: background-color 120ms", "transition: padding-left 120ms")), "--check", "transitions the layout property padding-left"),
    ("layout-3", "transition with no property (implicit all)", edit("css/flatcap-surfaces-motion.css", sub("transition: background-color 120ms cubic-bezier(0.2,0,0,1);", "transition: 120ms cubic-bezier(0.2,0,0,1);")), "--check", "transitions all of them"),
    ("layout-4", "@keyframes animating a layout property", edit("css/flatcap-quick-commands-motion.css", sub("to { opacity: 1; translate: 0 0; }", "to { opacity: 1; translate: 0 0; margin-left: 4px; }")), "--check", "animates the layout property margin-left"),
    ("zip-1", "ZIP timestamp", rezip("Flatcap-Slate.zip", date=(2026, 5, 5, 1, 2, 4)), "--check", "ZIP metadata date_time"),
    ("zip-2", "ZIP permissions", rezip("Flatcap-Slate.zip", attr=0o600 << 16), "--check", "ZIP metadata external_attr"),
    ("zip-3", "ZIP compression (stored)", rezip("Flatcap-Daylight.zip", compress=zipfile.ZIP_STORED), "--check", "ZIP metadata compress_type"),
    ("zip-4", "ZIP member name", rezip("Flatcap-Daylight.zip", member="theme/settings.json"), "--check", "members are"),
    ("zip-5", "ZIP extra member", rezip("Flatcap-Slate.zip", extra_member=True), "--check", "members are"),
    ("zip-6", "bytes outside the ZIP structure", trailing("Flatcap-Slate.zip"), "--check", "bytes outside the ZIP structure"),
    ("privacy-1", "Windows user path", edit("README.md", append(f"\n{WIN_PATH}\n")), "--check", "a Windows user path"),
    ("privacy-2", "home directory path", edit("docs/qa-report.md", append(f"\n{HOME_PATH}\n")), "--check", "a home directory path"),
    ("privacy-3", "RFC1918 10/8", edit("docs/mapping.md", append(f"\nhost {IP10}\n")), "--check", "RFC1918 10/8"),
    ("privacy-4", "RFC1918 172.16/12", edit("docs/mapping.md", append(f"\nhost {IP172}\n")), "--check", "RFC1918 172.16/12"),
    ("privacy-5", "RFC1918 192.168/16", edit("css/flatcap-downloads.css", append(f"\n/* {IP192} */\n")), "--check", "RFC1918 192.168/16"),
    ("privacy-6", "internal host name", edit("README.md", append(f"\nsee {HOST}\n")), "--check", "an internal host name"),
    ("markers-1", "opening marker missing", edit("README.md", sub("<!-- build:fonts -->\n", "")), "--check", "build:fonts"),
    ("markers-2", "closing marker missing", edit("docs/mapping.md", sub("<!-- /build:contrast -->", "")), "--check", "build:contrast"),
    ("markers-3", "marker duplicated", edit("docs/qa-report.md", append("\n<!-- build:zipcheck -->\n<!-- /build:zipcheck -->\n")), "--check", "build:zipcheck"),
    ("markers-4", "unexpected marker", edit("README.md", append("\n<!-- build:nonsense -->\n<!-- /build:nonsense -->\n")), "--check", "unexpected generated block marker"),
    ("sync-1", "--sync exits non-zero on a marker error", edit("README.md", sub("<!-- /build:layers -->", "")), "--sync", "build:layers"),
    ("sync-2", "--sync exits non-zero on a CSS error", edit("css/flatcap-audio-quiet.css", append("\n.tab-audio { opacity: 1; }\n")), "--sync", "without a Flatcap theme-id scope"),
    ("font-1", "font-size under 13px", edit("css/flatcap-quick-commands.css", sub("font-size: 13px; line-height: 16px;", "font-size: 12px; line-height: 16px;")), "--check", "is under 13px"),
    ("color-1", "color literal in a layer", edit("css/flatcap-quick-commands.css", sub("var(--fc-shadow-overlay)", "0 8px 24px rgb(0 0 0 / 24%)")), "--check", "holds a color literal"),
    ("order-1", "url-subtle loses its specificity (load-order dependence on the base)", edit("css/flatcap-url-subtle.css", lambda s: s.replace(".UrlBar-AddressField.UrlBar-AddressField", ".UrlBar-AddressField")), "--check", "depends on load order"),
    ("order-2", "extensions-list focus rule loses its specificity", edit("css/flatcap-extensions-list.css", sub(".extensionIconPopupMenu.extensionIconPopupMenu ", ".extensionIconPopupMenu ")), "--check", "depends on load order"),
    ("order-3", "motion redefines --fc-motion-fast at the same specificity as the base", edit("css/flatcap-motion.css", append("\n@media (prefers-reduced-motion: reduce) {\n " + UI + " { --fc-motion-fast: 0ms; }\n}\n")), "--check", "depends on load order"),
    ("example-1", "example without the NOT SCOPED notice", edit("examples/bookmark-bar-inline.css", sub("NOT SCOPED BY THEME ID", "scoped as you like")), "--check", "NOT SCOPED BY THEME ID"),
    ("stale-1", "base CSS edited by hand", edit("css/flatcap-ui.css", append("\n/* hand edit */\n")), "--check", "stale generated file: css/flatcap-ui.css"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="git ref to copy with git archive (default: the working tree)")
    a = ap.parse_args()
    rows, bad = [], 0
    for cid, what, mutate, cmd, want in CASES:
        with tempfile.TemporaryDirectory(prefix="flatcap-mut-") as t:
            d = Path(t)
            copy_tree(d, a.ref)
            if mutate:
                mutate(d)
            r = subprocess.run([sys.executable, "scripts/build.py", cmd], cwd=d, capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
        if want is None:
            ok = r.returncode == 0
        else:
            ok = r.returncode != 0 and re.search(re.escape(want), out) is not None
        bad += not ok
        first = next((ln for ln in out.splitlines() if want and want in ln), out.splitlines()[0] if out else "")
        rows.append((cid, what, f"{cmd} -> exit {r.returncode}", "PASS" if ok else "FAIL", first[:110]))
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    for r in rows:
        print(f"{r[0]:<{w[0]}}  {r[1]:<{w[1]}}  {r[2]:<{w[2]}}  {r[3]}  | {r[4]}")
    print(f"{len(rows) - bad}/{len(rows)} cases as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
