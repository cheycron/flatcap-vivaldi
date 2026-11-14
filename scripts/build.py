#!/usr/bin/env python3
"""Build Flatcap 2.0 for Vivaldi from src/theme.json (the Flatcap core) and src/vivaldi.json (port settings).

    python3 scripts/build.py --sync     write themes/*.zip, css/flatcap-ui.css and the generated blocks of README.md and docs/*.md;
                                        exit 1 (after writing) if the result does not pass the checks below
    python3 scripts/build.py --check    exit 1 on: a stale generated file, a missing or duplicated <!-- build:x --> marker, a ZIP whose
                                        content or metadata (members, date, permissions, compression) differs from the build, a CSS rule
                                        without a theme-id scope, a transition or animation of a layout property, a font-size under 13px,
                                        a color literal in a layer, two layers whose rules only win by load order, a private path, IP
                                        or host name, or a missed contrast target

Two kinds of output:
  * themes/Flatcap-Slate.zip and themes/Flatcap-Daylight.zip: the format Vivaldi exports from Settings > Themes > Library >
    Export Theme: a ZIP whose root holds settings.json (the theme parameters). No background image. The ZIPs are deterministic: a
    fixed timestamp, member order and attributes. --check compares every ZIP metadata field with what the build writes; the deflate
    stream itself depends on the zlib in use, so a different zlib may give other compressed bytes for the same content (reported as a
    note, not an error, as long as the sizes and metadata match).
  * css/flatcap-ui.css: the tokens (--fc-*) for each theme plus the core surface rules, scoped by theme id.
The other css/*.css files are written by hand (they are the optional layers); --check only validates them.
Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import color as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "src" / "theme.json"
PORT = ROOT / "src" / "vivaldi.json"
CSS_DIR = ROOT / "css"
PRIVATE_FILE = ROOT / ".private-patterns"  # local, git-ignored: one regular expression per line (see .private-patterns.example)
ZIP_DATE = (2026, 1, 1, 0, 0, 0)  # fixed: the ZIPs must not change with the build date
MODES = ("slate", "daylight")
PRIVACY = [  # generic patterns for strings that must never be committed: personal paths, private addresses, internal names, personal emails
    (r"[A-Za-z]:\\+Users", "a Windows user path"), (r"AppData", "an AppData path"),
    (r"/mnt/[A-Za-z0-9_.-]", "a /mnt path"), (r"/home/[A-Za-z0-9_.-]", "a home directory path"), (r"/Users/[A-Za-z0-9_.-]", "a macOS home path"),
    (r"(?<![\w\\:.])\\\\[A-Za-z0-9_-][\w.-]*\\+[\w$]", "a UNC path"),
    (r"\.review", "the private review folder"), (r"User Data", "a browser profile path"),
    (r"(?<![\d.])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 10/8)"),
    (r"(?<![\d.])172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 172.16/12)"),
    (r"(?<![\d.])192\.168\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 192.168/16)"),
    (r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?![\d.])", "a CGNAT / Tailscale IP (100.64/10)"),
    (r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:local|lan|internal|intranet|corp|home\.arpa)\b", "an internal host name"),
    (r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b", "a Tailscale host name (*.ts.net)"),
    (r"[A-Za-z0-9._%+-]+@(?!(?:[A-Za-z0-9-]+\.)*noreply\.github\.com\b)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", "an email address that is not a GitHub noreply one"),
]
LAYOUT_RE = re.compile(r"^(?:width|height|(?:min|max)-(?:width|height|inline-size|block-size)|inline-size|block-size|top|left|right|bottom|"
                       r"inset(?:-[a-z]+)*|margin(?:-[a-z]+)*|padding(?:-[a-z]+)*|(?:row-|column-)?gap|flex(?:-[a-z]+)*|grid(?:-[a-z]+)*|"
                       r"border(?:-[a-z]+)*-width|font-size|line-height|letter-spacing|position|display)$")
MIN_FONT_PX = 13  # the core's smallest text size (font.size.meta, 0.8125rem)
SHORTHANDS = ("border", "outline", "background", "transition", "animation", "margin", "padding", "font")
TIMING = {"ease", "ease-in", "ease-out", "ease-in-out", "linear", "step-start", "step-end", "normal", "allow-discrete"}
DOC_BLOCKS = {"README.md": ["themes", "layers", "fonts"],
              "docs/mapping.md": ["params", "zipcheck", "scope", "rules", "tokens", "contrast"],
              "docs/qa-report.md": ["zipcheck", "invariants"]}
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SCOPE_RE = re.compile(rf"^(?:#app )?#browser(?::is\(\.theme-id-{UUID}(?:,\.theme-id-{UUID})*\)|\.theme-id-{UUID})(?![\w-])")
LAYOUT_EXCEPTIONS = {("flatcap-surfaces-motion.css", "width")}  # Vivaldi's own overlay-panel width transition, retimed (see the QA report)
COLOR_TOKEN = re.compile(r"--fc-(bg|text|border|focus|accent|selection|success|warning|danger|info)-")


def load() -> dict:
    return json.loads(THEME.read_text(encoding="utf-8"))


def port() -> dict:
    return json.loads(PORT.read_text(encoding="utf-8"))


def layers(p: dict) -> list[dict]:
    return p["layers"]


# --- scope ---------------------------------------------------------------------------------------------------------

def ids(p: dict) -> dict[str, str]:
    return p["scope"]["ids"]


def scope_one(p: dict, mode: str) -> str:
    return f"#browser.theme-id-{ids(p)[mode]}"


def scope_all(p: dict) -> str:
    return "#browser:is(" + ",".join(f".theme-id-{ids(p)[m]}" for m in MODES) + ")"


# --- Vivaldi theme export (ZIP) ------------------------------------------------------------------------------------

def settings(theme: dict, p: dict, mode: str) -> dict:
    t = theme["themes"][mode]
    s = dict(p["theme_fixed"])
    s.update({k: t[role].upper() for k, role in p["theme_roles"].items()})
    s["accentSaturationLimit"] = p["themes"][mode]["accentSaturationLimit"]
    s["id"] = ids(p)[mode]
    s["name"] = p["themes"][mode]["name"]
    return dict(sorted(s.items()))


def settings_bytes(s: dict) -> bytes:
    return (json.dumps(s, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def zip_bytes(s: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("settings.json", date_time=ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3  # Unix: the same on every build host
        info.external_attr = 0o644 << 16
        z.writestr(info, settings_bytes(s), compresslevel=9)
    return buf.getvalue()


def zips(theme: dict, p: dict) -> dict[Path, dict]:
    return {ROOT / "themes" / p["themes"][m]["file"]: settings(theme, p, m) for m in MODES}


ZIP_FIELDS = ("filename", "date_time", "compress_type", "create_system", "create_version", "extract_version", "external_attr",
              "internal_attr", "flag_bits", "extra", "comment", "volume", "header_offset", "file_size", "CRC")


def zip_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    for path, want in zips(theme, p).items():
        rel = path.relative_to(ROOT)
        if not path.exists():
            errs.append(f"missing ZIP: {rel} (run --sync)")
            continue
        ref_bytes = zip_bytes(want)
        with zipfile.ZipFile(io.BytesIO(ref_bytes)) as rz:
            ref = rz.infolist()[0]
        raw_zip = path.read_bytes()
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    errs.append(f"{rel}: corrupt member {z.testzip()}")
                    continue
                infos = z.infolist()
                if [i.filename for i in infos] != ["settings.json"]:
                    errs.append(f"{rel}: members are {[i.filename for i in infos]}, expected only settings.json at the root")
                    continue
                info = infos[0]
                for f in ZIP_FIELDS:
                    if f == "filename":
                        continue
                    if getattr(info, f) != getattr(ref, f):
                        errs.append(f"{rel}: ZIP metadata {f} is {getattr(info, f)!r}, the build writes {getattr(ref, f)!r} "
                                    f"({'timestamp' if f == 'date_time' else 'permissions' if f == 'external_attr' else 'compression' if f == 'compress_type' else 'metadata'} altered, not deterministic)")
                if z.comment != b"":
                    errs.append(f"{rel}: ZIP has an archive comment")
                # no bytes outside the member and the directory (the compressed size may differ with another zlib)
                if len(raw_zip) != len(ref_bytes) - ref.compress_size + info.compress_size:
                    errs.append(f"{rel}: the file has bytes outside the ZIP structure (size {len(raw_zip)})")
                raw = z.read("settings.json")
        except zipfile.BadZipFile as e:
            errs.append(f"{rel}: not a ZIP ({e})")
            continue
        try:
            got = json.loads(raw)
        except ValueError as e:
            errs.append(f"{rel}: settings.json is not valid JSON ({e})")
            continue
        if got != want or raw != settings_bytes(want):
            errs.append(f"stale generated file: {rel} (run --sync)")
        elif raw_zip != ref_bytes and not any(e.startswith(str(rel)) for e in errs):
            print(f"note: {rel} differs byte for byte from a local rebuild but has the same content, metadata and size layout; "
                  f"expected only when this Python's zlib compresses differently", file=sys.stderr)
        for k in ("id", "name", "colorBg", "colorFg", "colorHighlightBg", "colorAccentBg", "colorWindowBg", "version", "engineVersion"):
            if k not in got:
                errs.append(f"{rel}: settings.json has no {k}")
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", str(got.get("id", ""))):
            errs.append(f"{rel}: id {got.get('id')!r} is not a UUID v4")
        if got.get("backgroundImage"):
            errs.append(f"{rel}: backgroundImage is set but the ZIP has no image")
    return errs


# --- css/flatcap-ui.css ---------------------------------------------------------------------------------------------

def tok(key: str) -> str:
    return "--fc-" + key.replace(".", "-")


def token_decls(theme: dict, mode: str) -> list[tuple[str, str]]:
    out = [(tok(k), v) for k, v in theme["themes"][mode].items()]
    out += [(tok(k), v) for k, v in theme["typography"].items()]
    out += [(tok(k), v) for k, v in theme["metrics"].items()]
    out += [(tok(k), v) for k, v in theme["elevation"][mode].items()]  # --fc-shadow-overlay, per theme
    return out


# (selector after the scope, {property: value}); values are var(--fc-*) references so the mapping table can be derived from them
BASE_RULES: list[tuple[str, dict[str, str]]] = [
    (" :is(.toolbar-mainbar,.bookmark-bar,#panels-container,.toolbar-statusbar)",
     {"background-color": "var(--fc-bg-surface)", "color": "var(--fc-text-primary)"}),
    (" :is(.UrlBar-AddressField,.SearchField)",
     {"background-color": "var(--fc-bg-canvas)", "color": "var(--fc-text-primary)", "border": "1px solid var(--fc-border-control)",
      "border-radius": "var(--fc-radius-control)"}),
    (" .tab-position .tab.active",
     {"background-color": "var(--fc-bg-selected)", "color": "var(--fc-text-primary)", "text-decoration": "none"}),
    (" .toolbar-mainbar .button-toolbar button:not(:disabled):hover",
     {"background-color": "var(--fc-bg-hover)", "color": "var(--fc-text-primary)"}),
    (" :is(button,input,select,textarea,[tabindex]):not(.UrlBar-AddressField input):focus-visible",
     {"outline": "var(--fc-focus-width) solid var(--fc-focus-ring)", "outline-offset": "var(--fc-focus-offset)"}),
    (" .UrlBar-AddressField:focus-within",
     {"outline": "var(--fc-focus-width) solid var(--fc-focus-ring)", "outline-offset": "calc(var(--fc-focus-width) * -1)"}),
    (" :is(input,textarea)::selection",
     {"background": "var(--fc-selection-bg)", "color": "var(--fc-selection-fg)"}),
]
CONTRAST_MORE = {"text.primary": "contrast.text.primary", "text.secondary": "contrast.text.secondary",
                 "text.muted": "contrast.text.muted", "border.control": "contrast.border.control"}


def base_css(theme: dict, p: dict) -> str:
    v = theme["version"]
    o = ["/*", f" * Flatcap for Vivaldi {v}: base tokens and core surfaces",
         " * Generated by scripts/build.py from src/theme.json (the Flatcap 2.0 core). Do not edit by hand.",
         " * Applies only while Flatcap Slate or Flatcap Daylight is the active theme (scoped by theme id, see docs/mapping.md).",
         " * The other css/ files use the --fc-* tokens defined here and must find this file in the same folder; the load order does not matter",
         " * (no layer relies on file order, see the same-specificity check in scripts/build.py).",
         " *", " * License: MIT (c) Cheycron Blaine. https://github.com/cheycron/flatcap-vivaldi", " */"]
    for m in MODES:
        o.append(f"{scope_one(p, m)} {{")
        o += [f"  {n}: {val};" for n, val in token_decls(theme, m)]
        o += ["  font-family: var(--fc-font-ui);", "}"]
    o += ["", "/* Vivaldi derives the text color on highlighted fills itself; use the Flatcap accent.on instead. */",
          f"{scope_all(p)} {{", "  --colorHighlightFg: var(--fc-accent-on) !important;", "}", "",
          "/* Increased contrast (operating system setting): the core's high-contrast set. */", "@media (prefers-contrast: more) {"]
    for m in MODES:
        o.append(f"  {scope_one(p, m)} {{")
        o += [f"    {tok(k)}: var({tok(c)});" for k, c in CONTRAST_MORE.items()]
        o.append("  }")
    o += ["}", "", "/* Core surfaces. Not applied in forced-colors mode: the system palette stays authoritative. */",
          "@media not (forced-colors: active) {"]
    for sel, props in BASE_RULES:
        o.append(f"  {scope_all(p)}{sel} {{")
        o += [f"    {k}: {val};" for k, val in props.items()]
        o.append("  }")
    o += ["}", "", "/* Ligatures change what you read in a URL. */", f"{scope_all(p)} .UrlBar-AddressField input {{",
          "  font-variant-ligatures: none;", "  font-feature-settings: normal;", "}", ""]
    return "\n".join(o)


def outputs(theme: dict, p: dict) -> dict[Path, str]:
    return {CSS_DIR / "flatcap-ui.css": base_css(theme, p)}


# --- CSS checks ----------------------------------------------------------------------------------------------------

def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def defined_tokens(css: str) -> set[str]:
    return set(re.findall(r"(--fc-[a-z0-9-]+)\s*:", css))


def css_files(p: dict) -> list[Path]:
    return [CSS_DIR / l["file"] for l in layers(p)]


def split_top(text: str, sep: str) -> list[str]:
    """Split on sep outside (), [] and quotes."""
    out, depth, cur, q = [], 0, [], ""
    for ch in text:
        if q:
            cur.append(ch)
            q = "" if ch == q else q
        elif ch in "\"'":
            q = ch
            cur.append(ch)
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def blocks(css: str) -> list[tuple[str, str]]:
    """Top-level (prelude, body) pairs of comment-free CSS."""
    out, depth, pre, body_start, prelude = [], 0, 0, 0, ""
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                prelude, body_start = css[pre:i].strip(), i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((prelude, css[body_start:i]))
                pre = i + 1
    return out


def walk(css: str, ctx: tuple = ()):
    """Yield (kind, prelude, body, ctx): kind is 'rule' or 'keyframes'. @media/@supports are entered, other at-rules are skipped."""
    for pre, body in blocks(css):
        if pre.startswith("@keyframes"):
            yield "keyframes", pre, body, ctx
        elif pre.startswith(("@media", "@supports", "@layer")):
            yield from walk(body, ctx + (pre,))
        elif pre.startswith("@"):
            continue
        else:
            yield "rule", pre, body, ctx


def decls(body: str) -> list[tuple[str, str]]:
    out = []
    for d in split_top(body, ";"):
        if ":" in d and not d.startswith("{"):
            k, v = d.split(":", 1)
            out.append((k.strip().lower(), v.strip()))
    return out


def is_layout(prop: str) -> bool:
    return bool(LAYOUT_RE.match(prop))


def transition_props(prop: str, value: str) -> tuple[list[str], bool]:
    """(property names a transition declaration names, whether it leaves the property implicit, which means 'all')."""
    names, implicit = [], False
    if prop == "transition-property":
        return [x.strip().lower() for x in value.split(",")], False
    for seg in split_top(value, ","):
        seg = re.sub(r"[a-z-]+\([^()]*(?:\([^()]*\)[^()]*)*\)", " ", seg.lower())
        toks = [t for t in seg.split() if not re.fullmatch(r"-?[\d.]+m?s", t) and t not in TIMING]
        if toks == ["none"]:
            continue
        if not toks:
            implicit = True
        names += toks
    return names, implicit


def spec(sel: str) -> tuple[int, int, int]:
    """Selector specificity (ids, classes/attributes/pseudo-classes, types), simplified: enough for this repository's selectors."""
    a = b = c = 0
    i, n = 0, len(sel)
    ident = re.compile(r"[\w-]+")
    while i < n:
        ch = sel[i]
        if ch == "#":
            a += 1
            i += 1 + (ident.match(sel, i + 1).end() - i - 1 if ident.match(sel, i + 1) else 0)
        elif ch == ".":
            b += 1
            m = ident.match(sel, i + 1)
            i = m.end() if m else i + 1
        elif ch == "[":
            b += 1
            i = sel.index("]", i) + 1
        elif ch == ":":
            pseudo_el = sel[i:i + 2] == "::"
            m = ident.match(sel, i + (2 if pseudo_el else 1))
            name = m.group(0).lower() if m else ""
            i = m.end() if m else i + 1
            args = None
            if i < n and sel[i] == "(":
                depth, j = 0, i
                while j < n:
                    depth += (sel[j] == "(") - (sel[j] == ")")
                    j += 1
                    if depth == 0:
                        break
                args, i = sel[i + 1:j - 1], j
            if pseudo_el:
                c += 1
            elif name in ("is", "not", "has", "matches") and args is not None:
                s = max((spec(x) for x in split_top(args, ",")), default=(0, 0, 0))
                a, b, c = a + s[0], b + s[1], c + s[2]
            elif name == "where":
                pass
            else:
                b += 1
        elif ch.isalpha() or ch == "_":
            c += 1
            i = ident.match(sel, i).end()
        else:
            i += 1
    return a, b, c


def subject(sel: str) -> frozenset[str]:
    """What the last compound selector can match: its classes, ids and tag names (also inside :is()), scope removed. {'<scope>'} means
    the scope element itself and {'*'} a compound with no class, id or tag (for example only a pseudo-class)."""
    s = re.sub(r"\.theme-id-" + UUID, "", sel)
    s = re.sub(r":is\(\s*(?:,\s*)*\)", "", s)
    s = re.sub(r":(?:not|has|where)\((?:[^()]|\([^()]*\))*\)", "", s)
    last = re.split(r"\s+|\s*[>+~]\s*", s.strip())[-1]
    if re.fullmatch(r"#browser|#app", last):
        return frozenset({"<scope>"})
    last = re.sub(r":is\(([^()]*)\)", r"|\1|", last)
    found = set(re.findall(r"[.#][\w-]+", last)) | set(re.findall(r"(?:^|[|,])([a-z][\w-]*)", last))
    found -= {"#browser", "#app"}
    return frozenset(found) if found else frozenset({"*"})


def overlap(a: frozenset[str], b: frozenset[str]) -> bool:
    if a & b:
        return True
    return ("*" in a and b != {"<scope>"}) or ("*" in b and a != {"<scope>"})


def conflicts(a: str, b: str) -> bool:
    """Two property names whose cascade fights (same name, or a shorthand against one of its longhands)."""
    if a == b:
        return True
    return any((a == sh and b.startswith(sh + "-")) or (b == sh and a.startswith(sh + "-")) for sh in SHORTHANDS)


def order_errors(p: dict) -> list[str]:
    """Rules of two different layer files that hit the same element and property with equal specificity: the winner would depend on the
    order Vivaldi reads the files. Pseudo-class rules and media blocks are compared as if they always applied (conservative)."""
    entries = []  # (file, selector, specificity, subject, properties)
    for l in layers(p):
        f = CSS_DIR / l["file"]
        if not f.exists():
            continue
        for kind, pre, body, ctx in walk(strip_comments(f.read_text(encoding="utf-8"))):
            if kind != "rule":
                continue
            props = {k: re.sub(r"\s+", " ", v) for k, v in decls(body)}
            for sel in split_top(pre, ","):
                entries.append((l["file"], sel, spec(sel), subject(sel), props))
    errs = []
    for i, (fa, sa, pa, ja, ka) in enumerate(entries):
        for fb, sb, pb, jb, kb in entries[i + 1:]:
            if fa == fb or pa != pb or not overlap(ja, jb):
                continue
            both = sorted({x for x in ka for y in kb if conflicts(x, y) and ka[x] != kb[y]} | {y for x in ka for y in kb if conflicts(x, y) and ka[x] != kb[y]})
            if both:
                errs.append(f"{fa} and {fb}: same specificity {pa} on the same element for {', '.join(both)} ('{sa}' / '{sb}'): "
                            f"the result depends on load order")
    return errs


def check_css(theme: dict, p: dict) -> list[str]:
    errs = []
    known_ids = set(ids(p).values())
    base = (CSS_DIR / "flatcap-ui.css")
    defined = defined_tokens(base.read_text(encoding="utf-8")) if base.exists() else set()
    listed = {l["file"] for l in layers(p)}
    for f in sorted(CSS_DIR.glob("*.css")):
        if f.name not in listed:
            errs.append(f"css/{f.name} is not listed in src/vivaldi.json")
    for l in layers(p):
        f = CSS_DIR / l["file"]
        n = l["file"]
        if not f.exists():
            errs.append(f"css/{n} is listed but missing")
            continue
        raw = f.read_text(encoding="utf-8")
        css = strip_comments(raw)
        head = raw[:raw.find("*/") + 2] if raw.startswith("/*") else ""
        if f"Flatcap for Vivaldi {theme['version']}" not in head:
            errs.append(f"css/{n}: header must name 'Flatcap for Vivaldi {theme['version']}'")
        lic = "License: MIT" if l["license"] == "MIT" else "License: GPL-3.0"
        if lic not in head:
            errs.append(f"css/{n}: header must state '{lic}'")
        if l["license"] == "GPL-3.0" and not (ROOT / "LICENSES" / "GPL-3.0.txt").exists():
            errs.append(f"css/{n} is GPL-3.0 but LICENSES/GPL-3.0.txt is missing")
        if css.count("{") != css.count("}") or css.count("(") != css.count(")"):
            errs.append(f"css/{n}: unbalanced braces or parentheses")
        if re.search(r"transition(-property)?\s*:[^;{}]*\ball\b", css):
            errs.append(f"css/{n}: 'transition: all' is not allowed")
        for u in re.findall(r"theme-id-([0-9a-f-]{36})", css):
            if u not in known_ids:
                errs.append(f"css/{n}: scoped to an unknown theme id {u}")
        if not l.get("base") and "theme-id-" not in css:
            errs.append(f"css/{n}: not scoped by a Flatcap theme id")
        for t in sorted(set(re.findall(r"var\((--fc-[a-z0-9-]+)", css)) - defined):
            errs.append(f"css/{n}: {t} is not defined in flatcap-ui.css")
        if re.search(r"@keyframes|animation\s*:|animation-name|transition", css) and "prefers-reduced-motion" not in css:
            errs.append(f"css/{n}: animates or transitions but has no prefers-reduced-motion rule")
        if COLOR_TOKEN.search(css) and "forced-colors" not in css:
            errs.append(f"css/{n}: paints with color tokens but has no forced-colors guard")
        for kind, pre, body, ctx in walk(css):
            if kind == "keyframes":
                for _, kb in blocks(body):
                    for prop, _v in decls(kb):
                        if is_layout(prop) and (n, prop) not in LAYOUT_EXCEPTIONS:
                            errs.append(f"css/{n}: {pre} animates the layout property {prop}")
                continue
            for sel in split_top(pre, ","):
                if not SCOPE_RE.match(sel):
                    errs.append(f"css/{n}: selector without a Flatcap theme-id scope: {sel[:90]}")
            for prop, val in decls(body):
                if prop in ("transition", "transition-property"):
                    names, implicit = transition_props(prop, val)
                    if implicit:
                        errs.append(f"css/{n}: '{prop}: {val[:40]}' names no property, which transitions all of them")
                    for name in names:
                        if is_layout(name) and (n, name) not in LAYOUT_EXCEPTIONS:
                            errs.append(f"css/{n}: transitions the layout property {name}")
                if prop in ("animation", "animation-name") and re.search(r"(?<![\w-])all(?![\w-])", val):
                    errs.append(f"css/{n}: animation names 'all'")
                if prop == "font-size":
                    m = re.fullmatch(r"([\d.]+)(px|rem)", val.strip())
                    if m:
                        px = float(m.group(1)) * (16 if m.group(2) == "rem" else 1)
                        if px < MIN_FONT_PX:
                            errs.append(f"css/{n}: font-size {val} is under {MIN_FONT_PX}px")
                    elif not val.startswith("var(--fc-font-size-") and val not in ("inherit", "initial", "unset"):
                        errs.append(f"css/{n}: font-size {val} cannot be checked against {MIN_FONT_PX}px (use px, rem or a --fc-font-size token)")
                if not l.get("base") and re.search(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch|hwb|color-mix)\(", val):
                    errs.append(f"css/{n}: '{prop}' holds a color literal; use a --fc-* token ({val[:50]})")
    return errs + order_errors(p)


def example_errors() -> list[str]:
    """examples/ is exempt from the scope rule on purpose; the file must say so, so nobody mistakes it for a layer."""
    errs = []
    for f in sorted((ROOT / "examples").glob("*.css")):
        head = f.read_text(encoding="utf-8")[:3000]
        if "NOT SCOPED BY THEME ID" not in head or "NOT A RELEASED LAYER" not in head:
            errs.append(f"examples/{f.name}: the header must say 'NOT A RELEASED LAYER' and 'NOT SCOPED BY THEME ID'")
    return errs


def marker_errors() -> list[str]:
    errs = []
    for rel, want in DOC_BLOCKS.items():
        path = ROOT / rel
        if not path.exists():
            errs.append(f"{rel}: missing (it carries generated blocks)")
            continue
        text = path.read_text(encoding="utf-8")
        found = re.findall(r"<!--\s*/?build:([\w-]+)\s*-->", text)
        for name in sorted(set(found) - set(want)):
            errs.append(f"{rel}: unexpected generated block marker 'build:{name}'")
        for name in want:
            o, c = text.count(f"<!-- build:{name} -->"), text.count(f"<!-- /build:{name} -->")
            if o != 1 or c != 1:
                errs.append(f"{rel}: marker <!-- build:{name} --> found {o}x and its closing marker {c}x, expected 1 and 1")
            elif text.index(f"<!-- build:{name} -->") > text.index(f"<!-- /build:{name} -->"):
                errs.append(f"{rel}: build:{name} closes before it opens")
    return errs


def invariant_rows(p: dict) -> list[tuple[str, ...]]:
    rows = []
    for l in layers(p):
        f = CSS_DIR / l["file"]
        if not f.exists():
            continue
        css = strip_comments(f.read_text(encoding="utf-8"))
        uses_color = bool(COLOR_TOKEN.search(css)) or "background" in css
        animates = bool(re.search(r"@keyframes|animation\s*:|animation-name|transition", css))
        unscoped = sum(1 for k, pre, _b, _c in walk(css) if k == "rule" for sel in split_top(pre, ",") if not SCOPE_RE.match(sel))
        sizes = [v for k, pre, body, _c in walk(css) if k == "rule" for pr, v in decls(body) if pr == "font-size"]
        rows.append((l["file"], "yes" if "forced-colors" in css else ("n/a" if not uses_color else "**no**"),
                     "yes" if "prefers-reduced-motion" in css else ("n/a" if not animates else "**no**"),
                     "no" if not re.search(r"transition(-property)?\s*:[^;{}]*\ball\b", css) else "**yes**",
                     "yes (retimed native panel width, not while dragging)" if l["file"] == "flatcap-surfaces-motion.css" else "no",
                     "none" if not unscoped else f"**{unscoped}**", ", ".join(sorted(set(sizes))) or "(none set)"))
    return rows


def private_patterns() -> tuple[list[tuple[re.Pattern, str]], list[str]]:
    """Names of the maintainer's own machines, domains and users: kept out of the repository, in a local file that git ignores
    (.private-patterns, or the file FLATCAP_PRIVATE_PATTERNS points to). One regular expression per line, # starts a comment."""
    env = os.environ.get("FLATCAP_PRIVATE_PATTERNS")
    path = Path(env) if env else PRIVATE_FILE
    if not path.is_file():
        return [], ([f"FLATCAP_PRIVATE_PATTERNS points to a file that does not exist ({path.name})"] if env else [])
    pats, errs = [], []
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            try:
                pats.append((re.compile(ln, re.I), f"a private pattern (line {n} of {path.name})"))
            except re.error as ex:
                errs.append(f"{path.name} line {n}: not a valid regular expression ({ex})")
    return pats, errs


def core_sha256() -> str:
    return hashlib.sha256(THEME.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # line endings must not matter on a Windows checkout


def core_errors(p: dict) -> list[str]:
    pin = p.get("core", {}).get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", pin):
        return ["src/vivaldi.json: core.sha256 (the pinned SHA-256 of src/theme.json) is missing or not a SHA-256"]
    got = core_sha256()
    if got != pin:
        return [f"src/theme.json differs from the pinned core copy (SHA-256 {got}, src/vivaldi.json pins {pin}). A core change is taken on "
                f"purpose: copy the file from {p['core']['repo']}, run --pin-core, then --sync"]
    return []


def privacy_errors(p: dict) -> list[str]:
    errs = []
    private, perrs = private_patterns()
    errs += perrs
    files = [x for x in ROOT.rglob("*") if x.is_file() and ".git" not in x.relative_to(ROOT).parts
             and not {".review", "__pycache__", ".tmp", "node_modules"} & set(x.relative_to(ROOT).parts)]
    for f in files:
        rel = f.relative_to(ROOT)
        if rel.as_posix() in ("scripts/build.py", "LICENSES/GPL-3.0.txt", ".gitignore", PRIVATE_FILE.name):
            continue
        if f.suffix == ".zip":
            with zipfile.ZipFile(f) as z:
                data = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
        elif f.suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"):
            continue
        else:
            data = f.read_text(encoding="utf-8", errors="replace")
        for pat, what in PRIVACY:
            if re.search(pat, data):
                errs.append(f"{rel}: contains {what} ({pat})")
        for rx, what in private:  # the pattern itself is not printed: it is private
            if rx.search(data):
                errs.append(f"{rel}: contains {what}")
    return errs


# --- contrast ------------------------------------------------------------------------------------------------------

def pairs(theme: dict) -> list[tuple[str, str, str, str, float, str, float]]:
    """(mode, label, fg, bg, target, group, fg opacity). Roles are the pairs Vivaldi's UI combines with the Flatcap CSS."""
    out = []
    for m in MODES:
        t = theme["themes"][m]
        g = t.__getitem__

        def add(label, fg, bg, target, group, op=1.0):
            out.append((m, label, g(fg), g(bg), target, group, op))
        for s, where in (("canvas", "window, tab bar, address and search fields"), ("surface", "toolbars, bookmark bar, panels, status bar"),
                         ("raised", "Quick Commands, expanded extensions group, active tab (minimal tabs)"),
                         ("hover", "toolbar button hover, hovered tab, extension toggle"), ("selected", "active tab, selected Quick Command row")):
            add(f"text.primary on bg.{s} ({where})", "text.primary", f"bg.{s}", 7.0, "text")
        for s, where in (("canvas", "inactive tab on the tab bar"), ("surface", "section headers, shortcut chips, inactive tab"),
                         ("raised", "Quick Commands URL line"), ("hover", "hovered Quick Commands row"),
                         ("selected", "URL line of the selected Quick Command")):
            add(f"text.secondary on bg.{s} ({where})", "text.secondary", f"bg.{s}", 5.0, "text")
        add("text.primary at 85% on bg.surface (download file size)", "text.primary", "bg.surface", 5.0, "text", 0.85)
        add("text.primary at 85% on bg.hover (hovered download row)", "text.primary", "bg.hover", 5.0, "text", 0.85)
        add("accent.on on accent.fill (text on highlighted fills, --colorHighlightFg)", "accent.on", "accent.fill", 4.5, "fill")
        add("selection.fg on selection.bg (selected text in fields)", "selection.fg", "selection.bg", 4.5, "fill")
        for s in ("canvas", "surface", "raised", "hover", "selected"):
            add(f"focus.ring on bg.{s} (2px focus ring, selected-row bar, address field focus)", "focus.ring", f"bg.{s}", 3.0, "focus")
        add("border.control on bg.canvas (address and search field border, field fill)", "border.control", "bg.canvas", 3.0, "outline")
        add("border.control on bg.surface (address and search field border, bar)", "border.control", "bg.surface", 3.0, "outline")
        add("accent.fill on border.subtle (download progress fill vs its track)", "accent.fill", "border.subtle", 3.0, "outline")
        add("accent.fill on bg.surface (download progress fill vs panel)", "accent.fill", "bg.surface", 3.0, "outline")
        add("border.subtle on bg.canvas (address field at rest with flatcap-url-subtle.css, report only)", "border.subtle", "bg.canvas", 1.0, "report")
        add("border.subtle on bg.surface (address field at rest with flatcap-url-subtle.css, report only)", "border.subtle", "bg.surface", 1.0, "report")
        add("bg.canvas on bg.surface (address field fill vs bar, report only)", "bg.canvas", "bg.surface", 1.0, "report")
    return out


def ratio(fg: str, bg: str, op: float = 1.0) -> float:
    f, b = C.parse(fg), C.parse(bg)
    if op < 1.0:
        f = C.over((*f[:3], op), b)
    return C.contrast(f, b)


def rows(theme: dict) -> list[dict]:
    return [{"mode": m, "label": lab, "fg": fg, "bg": bg, "target": tg, "group": gr, "op": op, "ratio": ratio(fg, bg, op)}
            for m, lab, fg, bg, tg, gr, op in pairs(theme)]


def contrast_errors(theme: dict) -> list[str]:
    return [f"{r['mode']}: {r['label']} = {r['ratio']:.2f} < {r['target']}" for r in rows(theme) if r["ratio"] < r["target"]]


def validate_core(theme: dict, p: dict) -> list[str]:
    errs = core_errors(p)
    if theme.get("version") != "2.0.0":
        errs.append(f"src/theme.json version is {theme.get('version')}, expected 2.0.0")
    if p.get("version") != theme.get("version"):
        errs.append(f"src/vivaldi.json version {p.get('version')} differs from the core {theme.get('version')}")
    for m in MODES:
        for role in set(p["theme_roles"].values()) | {"accent.on", "selection.bg", "selection.fg", "focus.ring"}:
            if not C.is_hex(theme["themes"][m].get(role, "")):
                errs.append(f"{m}: missing or non-hex {role}")
    if ids(p)["slate"] == ids(p)["daylight"]:
        errs.append("the two themes share an id")
    return errs


# --- generated doc blocks ------------------------------------------------------------------------------------------

def md_themes(theme: dict, p: dict) -> str:
    r = ["| File | Theme | Mode | Accent |", "| :--- | :--- | :--- | :--- |"]
    for m, mode in (("slate", "dark"), ("daylight", "light")):
        r.append(f"| `themes/{p['themes'][m]['file']}` | {p['themes'][m]['name']} | {mode} | `{theme['themes'][m]['accent.fill']}` |")
    return "\n".join(r)


def md_layers(theme: dict, p: dict) -> str:
    r = ["| File | What it does | Needs `flatcap-ui.css` | License |", "| :--- | :--- | :--- | :--- |"]
    for l in layers(p):
        r.append(f"| `css/{l['file']}` | **{l['title']}.** {l['summary']} | {'(it is the base)' if l.get('base') else 'yes'} | {l['license']} |")
    return "\n".join(r)


def md_fonts(theme: dict, p: dict) -> str:
    f = theme["typography"]["font.ui"]
    return ("| Use | Stack (exact) |\n| :--- | :--- |\n"
            f"| Browser interface (`--fc-font-ui`, set on `#browser`) | `{f}` |\n\n"
            "The CSS does not install fonts. Without IBM Plex Sans on the device, the stack falls back to Segoe UI, then the system UI font. "
            "The themes themselves carry no font: fonts are set by `flatcap-ui.css` and, if you also set one in *Settings → Appearance*, "
            "Vivaldi's own font setting applies to web content only.")


def md_params(theme: dict, p: dict) -> str:
    L = ["| `settings.json` key | Flatcap role | Slate | Daylight |", "| :--- | :--- | :--- | :--- |"]
    for k, role in p["theme_roles"].items():
        L.append(f"| `{k}` | `{role}` | `{theme['themes']['slate'][role].upper()}` | `{theme['themes']['daylight'][role].upper()}` |")
    L.append(f"| `accentSaturationLimit` | (theme setting) | `{p['themes']['slate']['accentSaturationLimit']}` | `{p['themes']['daylight']['accentSaturationLimit']}` |")
    L.append(f"| `id` | (theme identity, see Scoping) | `{ids(p)['slate']}` | `{ids(p)['daylight']}` |")
    L.append(f"| `name` | (visible name) | {p['themes']['slate']['name']} | {p['themes']['daylight']['name']} |")
    L += ["", "Fixed parameters (the same in both themes): " + ", ".join(f"`{k}`: `{json.dumps(v)}`" for k, v in sorted(p["theme_fixed"].items())) + "."]
    return "\n".join(L)


def md_rules(theme: dict, p: dict) -> str:
    L = ["| Selector (after the scope) | Property | Token | Role |", "| :--- | :--- | :--- | :--- |"]
    for sel, props in BASE_RULES:
        for prop, val in props.items():
            tk = re.findall(r"--fc-[a-z0-9-]+", val)
            role = ", ".join(f"`{t[5:].replace('-', '.', 1)}`" for t in tk if COLOR_TOKEN.match(t)) or "(metric)"
            L.append(f"| `{sel.strip()}` | `{prop}` | `{val}` | {role} |")
    L.append("| `.UrlBar-AddressField input` | `font-variant-ligatures`, `font-feature-settings` | `none`, `normal` | (no ligatures in URLs) |")
    L.append("| scope | `--colorHighlightFg` (`!important`) | `var(--fc-accent-on)` | `accent.on` |")
    return "\n".join(L)


def md_scope(theme: dict, p: dict) -> str:
    return (f"`{scope_all(p)}`, that is `#browser.theme-id-{ids(p)['slate']}` (Slate) and `#browser.theme-id-{ids(p)['daylight']}` (Daylight).")


def md_tokens(theme: dict, p: dict) -> str:
    L = ["| File | Tokens used |", "| :--- | :--- |"]
    for l in layers(p):
        f = CSS_DIR / l["file"]
        if f.exists() and not l.get("base"):
            toks = sorted(set(re.findall(r"var\((--fc-[a-z0-9-]+)", strip_comments(f.read_text(encoding="utf-8")))))
            L.append(f"| `{l['file']}` | {', '.join(f'`{t}`' for t in toks) or '(none)'} |")
    return "\n".join(L)


def md_contrast(theme: dict, p: dict) -> str:
    L = ["| Theme | Pair | Ratio | Target | Result |", "| :--- | :--- | ---: | ---: | :--- |"]
    for r in rows(theme):
        res = "report only" if r["group"] == "report" else ("pass" if r["ratio"] >= r["target"] else "**FAIL**")
        tg = "-" if r["group"] == "report" else f"{r['target']:g}"
        L.append(f"| {r['mode']} | {r['label']} `{r['fg'].upper()}` / `{r['bg'].upper()}` | {r['ratio']:.2f} | {tg} | {res} |")
    return "\n".join(L)


def md_invariants(theme: dict, p: dict) -> str:
    L = ["| File | forced-colors guard | reduced-motion guard | `transition: all` | Transitions a layout property | Selectors outside the theme-id scope | `font-size` values |",
         "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
    L += [f"| `{a}` | {b} | {c} | {d} | {e} | {f} | {g} |" for a, b, c, d, e, f, g in invariant_rows(p)]
    return "\n".join(L)


def md_zipcheck(theme: dict, p: dict) -> str:
    L = ["| ZIP | Members | `id` | `name` | Timestamp |", "| :--- | :--- | :--- | :--- | :--- |"]
    for path, s in zips(theme, p).items():
        L.append(f"| `themes/{path.name}` | `settings.json` | `{s['id']}` | {s['name']} | {'-'.join(f'{x:02d}' for x in ZIP_DATE[:3])} (fixed) |")
    return "\n".join(L)


BLOCKS = {"themes": md_themes, "layers": md_layers, "fonts": md_fonts, "params": md_params, "rules": md_rules, "scope": md_scope,
          "tokens": md_tokens, "contrast": md_contrast, "invariants": md_invariants, "zipcheck": md_zipcheck}
DOCS = [ROOT / "README.md", ROOT / "docs" / "mapping.md", ROOT / "docs" / "qa-report.md"]


def render(path: Path, theme: dict, p: dict) -> str:
    text = path.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- build:{name} -->)\n?.*?\n?(<!-- /build:{name} -->)", re.S)
        text = pat.sub(lambda m: m.group(1) + "\n" + fn(theme, p) + "\n" + m.group(2), text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sync", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--pin-core", action="store_true")
    a = ap.parse_args()
    if a.pin_core:
        text = PORT.read_text(encoding="utf-8")
        new, n = re.subn(r'("sha256": ")[0-9a-f]{64}(")', lambda m: m.group(1) + core_sha256() + m.group(2), text)
        if n != 1:
            print("src/vivaldi.json: expected exactly one core.sha256 to rewrite")
            return 1
        PORT.write_text(new, encoding="utf-8")
        print(f"pinned src/theme.json: {core_sha256()}")
        return 0
    theme, p = load(), port()
    errs = validate_core(theme, p)
    outs = outputs(theme, p)
    if a.sync:
        errs += marker_errors()
        (ROOT / "themes").mkdir(exist_ok=True)
        CSS_DIR.mkdir(exist_ok=True)
        for path, s in zips(theme, p).items():
            path.write_bytes(zip_bytes(s))
        for path, css in outs.items():
            path.write_text(css, encoding="utf-8")
        if not marker_errors():
            for d in DOCS:
                d.write_text(render(d, theme, p), encoding="utf-8")
        print("synced:", ", ".join(x.name for x in [*zips(theme, p), *outs]))
        errs += zip_errors(theme, p) + check_css(theme, p) + example_errors() + privacy_errors(p) + contrast_errors(theme)
        if errs:
            print("\n".join("ERROR " + e for e in sorted(set(errs))))
            return 1
        return 0
    errs += marker_errors()
    stale = []
    for path, css in outs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != css:
            stale.append(str(path.relative_to(ROOT)))
    if not marker_errors():
        for d in DOCS:
            if d.read_text(encoding="utf-8") != render(d, theme, p):
                stale.append(str(d.relative_to(ROOT)))
    errs += [f"stale generated file: {s} (run --sync)" for s in stale]
    errs += zip_errors(theme, p) + check_css(theme, p) + example_errors() + privacy_errors(p) + contrast_errors(theme)
    if errs:
        print("\n".join(sorted(set(errs))))
        return 1
    n_rows = len([r for r in rows(theme) if r["group"] != "report"])
    print(f"ok: {len(zips(theme, p))} theme ZIPs (content and metadata as built), {len(layers(p))} CSS files (header, license, theme-id scope on every "
          f"rule, defined tokens, no color literals, font-size >= {MIN_FONT_PX}px, forced-colors and reduced-motion guards, no transition: all, "
          f"no layout transition or animation, no load-order dependence), {len(DOCS)} docs current with their markers, no private paths, IPs, "
          f"hosts or emails, core copy pinned by SHA-256, {n_rows} contrast targets met ({len(rows(theme)) - n_rows} report-only rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
