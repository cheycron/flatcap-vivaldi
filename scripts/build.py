#!/usr/bin/env python3
"""Build Flatcap 2.0 for Vivaldi from src/theme.json (the Flatcap core) and src/vivaldi.json (port settings).

    python3 scripts/build.py --sync     write themes/*.zip, css/flatcap-ui.css and the generated blocks of README.md and docs/*.md
    python3 scripts/build.py --check    fail on: a stale generated file, a ZIP that is not a valid Vivaldi theme export, a CSS file that
                                        breaks the Flatcap invariants (see check_css), a personal path or profile string, or a missed
                                        contrast target

Two kinds of output:
  * themes/Flatcap-Slate.zip and themes/Flatcap-Daylight.zip: the format Vivaldi exports from Settings > Themes > Library >
    Export Theme: a ZIP whose root holds settings.json (the theme parameters). No background image. The ZIPs are deterministic: a
    fixed timestamp, member order and attributes, so the same input gives the same bytes on the same Python/zlib.
  * css/flatcap-ui.css: the tokens (--fc-*) for each theme plus the core surface rules, scoped by theme id.
The other css/*.css files are written by hand (they are the optional layers); --check only validates them.
Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import io
import json
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
ZIP_DATE = (2026, 1, 1, 0, 0, 0)  # fixed: the ZIPs must not change with the build date
MODES = ("slate", "daylight")
PRIVACY = [  # strings that must never be committed (personal paths and profile data)
    (r"[A-Za-z]:\\+Users", "a Windows user path"), (r"AppData", "an AppData path"), (r"/mnt/appdata", "a local server path"),
    (r"/home/[a-z]", "a home directory path"), (r"\.review", "the private review folder"), (r"User Data", "a browser profile path"),
]
LAYOUT_PROPS = {"width", "height", "min-width", "max-width", "min-height", "max-height", "top", "left", "right", "bottom", "margin",
                "padding", "inset", "gap", "flex", "flex-basis", "grid-template-columns", "grid-template-rows"}
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


def zip_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    for path, want in zips(theme, p).items():
        rel = path.relative_to(ROOT)
        if not path.exists():
            errs.append(f"missing ZIP: {rel} (run --sync)")
            continue
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    errs.append(f"{rel}: corrupt member {z.testzip()}")
                    continue
                infos = z.infolist()
                if [i.filename for i in infos] != ["settings.json"]:
                    errs.append(f"{rel}: members are {[i.filename for i in infos]}, expected only settings.json at the root")
                    continue
                if infos[0].date_time != ZIP_DATE:
                    errs.append(f"{rel}: timestamp {infos[0].date_time} is not the fixed {ZIP_DATE} (not deterministic)")
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
         " * The other css/ files use the --fc-* tokens defined here, so load this one first (keep it in the same folder).",
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
        for m in re.finditer(r"transition(?:-property)?\s*:\s*([^;}]*)", css):
            for prop in re.findall(r"(?<![\w-])([a-z-]+)(?=\s|,|$)", m.group(1)):
                if prop in LAYOUT_PROPS and (n, prop) not in LAYOUT_EXCEPTIONS:
                    errs.append(f"css/{n}: transitions the layout property {prop}")
    return errs


def invariant_rows(p: dict) -> list[tuple[str, str, str, str, str]]:
    rows = []
    for l in layers(p):
        f = CSS_DIR / l["file"]
        if not f.exists():
            continue
        css = strip_comments(f.read_text(encoding="utf-8"))
        uses_color = bool(COLOR_TOKEN.search(css)) or "background" in css
        animates = bool(re.search(r"@keyframes|animation\s*:|animation-name|transition", css))
        rows.append((l["file"], "yes" if "forced-colors" in css else ("n/a" if not uses_color else "**no**"),
                     "yes" if "prefers-reduced-motion" in css else ("n/a" if not animates else "**no**"),
                     "no" if not re.search(r"transition(-property)?\s*:[^;{}]*\ball\b", css) else "**yes**",
                     "yes (retimed native panel width, not while dragging)" if l["file"] == "flatcap-surfaces-motion.css" else "no"))
    return rows


def privacy_errors(p: dict) -> list[str]:
    errs = []
    files = [x for x in ROOT.rglob("*") if x.is_file() and ".git" not in x.relative_to(ROOT).parts
             and not {".review", "__pycache__", ".tmp", "node_modules"} & set(x.relative_to(ROOT).parts)]
    for f in files:
        rel = f.relative_to(ROOT)
        if rel.as_posix() in ("scripts/build.py", "LICENSES/GPL-3.0.txt", ".gitignore"):
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
            add(f"focus.ring on bg.{s} (2px focus ring, selected-row bar)", "focus.ring", f"bg.{s}", 3.0, "focus")
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
    errs = []
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
    L = ["| File | forced-colors guard | reduced-motion guard | `transition: all` | Transitions a layout property |", "| :--- | :--- | :--- | :--- | :--- |"]
    L += [f"| `{a}` | {b} | {c} | {d} | {e} |" for a, b, c, d, e in invariant_rows(p)]
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
    a = ap.parse_args()
    theme, p = load(), port()
    errs = validate_core(theme, p)
    outs = outputs(theme, p)
    if a.sync:
        (ROOT / "themes").mkdir(exist_ok=True)
        CSS_DIR.mkdir(exist_ok=True)
        for path, s in zips(theme, p).items():
            path.write_bytes(zip_bytes(s))
        for path, css in outs.items():
            path.write_text(css, encoding="utf-8")
        for d in DOCS:
            if d.exists():
                d.write_text(render(d, theme, p), encoding="utf-8")
        print("synced:", ", ".join(x.name for x in [*zips(theme, p), *outs]))
        errs += check_css(theme, p) + contrast_errors(theme)
        for e in errs:
            print("WARN", e)
        return 0
    stale = []
    for path, css in outs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != css:
            stale.append(str(path.relative_to(ROOT)))
    for d in DOCS:
        if d.exists() and d.read_text(encoding="utf-8") != render(d, theme, p):
            stale.append(str(d.relative_to(ROOT)))
    errs += [f"stale generated file: {s} (run --sync)" for s in stale]
    errs += zip_errors(theme, p) + check_css(theme, p) + privacy_errors(p) + contrast_errors(theme)
    if errs:
        print("\n".join(sorted(set(errs))))
        return 1
    n_rows = len([r for r in rows(theme) if r["group"] != "report"])
    print(f"ok: {len(zips(theme, p))} theme ZIPs (settings.json, fixed timestamp, UUID v4 ids), {len(layers(p))} CSS files "
          f"(header, license, scope ids, defined tokens, forced-colors and reduced-motion guards, no transition: all), "
          f"{len([d for d in DOCS if d.exists()])} docs current, no personal paths, {n_rows} contrast targets met "
          f"({len(rows(theme)) - n_rows} report-only rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
