# QA report: Flatcap 2.0 for Vivaldi

Two parts. **Part A** is the build check: it runs without Vivaldi, on every push (`.github/workflows/validate.yml`), and its result is reproduced below. **Part B** is the live QA in a real Vivaldi: **pending**. Nothing in Part B has been checked yet, and the README says "not tested" for it.

## Part A: build check

`python3 scripts/build.py --check` verifies:

- the generated files (`themes/*.zip`, `css/flatcap-ui.css`, the generated blocks of README and docs) are current;
- each ZIP opens, holds only `settings.json` at its root, has the fixed timestamp, valid JSON, a UUID v4 `id`, the visible `name` and the colors of the core, and no background image;
- every CSS file is listed in `src/vivaldi.json`, has the header (version and license), is scoped to the two theme ids, balances its braces, uses only `--fc-*` tokens that `flatcap-ui.css` defines, has no `transition: all`, transitions no layout property (one documented exception), has a `prefers-reduced-motion` rule when it animates and a `forced-colors` guard when it paints with color tokens;
- no personal path or profile string appears in any committed file or inside a ZIP;
- every contrast target in [docs/mapping.md](mapping.md#5-contrast) is met.

### ZIPs

<!-- build:zipcheck -->
| ZIP | Members | `id` | `name` | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
| `themes/Flatcap-Slate.zip` | `settings.json` | `77d85a94-0f14-4fe6-88b6-2fcf00200001` | Flatcap Slate | 2026-01-01 (fixed) |
| `themes/Flatcap-Daylight.zip` | `settings.json` | `77d85a94-0f14-4fe6-88b6-2fcf00200002` | Flatcap Daylight | 2026-01-01 (fixed) |
<!-- /build:zipcheck -->

### CSS invariants (static)

<!-- build:invariants -->
| File | forced-colors guard | reduced-motion guard | `transition: all` | Transitions a layout property |
| :--- | :--- | :--- | :--- | :--- |
| `flatcap-ui.css` | yes | n/a | no | no |
| `flatcap-quick-commands.css` | yes | n/a | no | no |
| `flatcap-quick-commands-motion.css` | yes | yes | no | no |
| `flatcap-motion.css` | yes | yes | no | no |
| `flatcap-surfaces-motion.css` | yes | yes | no | yes (retimed native panel width, not while dragging) |
| `flatcap-tabs-minimal.css` | yes | n/a | no | no |
| `flatcap-url-subtle.css` | yes | n/a | no | no |
| `flatcap-audio-quiet.css` | yes | n/a | no | no |
| `flatcap-downloads.css` | yes | n/a | no | no |
| `flatcap-extensions-list.css` | yes | n/a | no | no |
| `flatcap-extensions-inline.css` | yes | yes | no | no |
<!-- /build:invariants -->

`flatcap-surfaces-motion.css` is the one layer that transitions a layout property: `width` of the overlay panel group, which is Vivaldi's own native transition with its timing replaced (140ms). It is not applied while the panel is being resized (`:has(.resizing)`), it only affects the overlay panel, and it is off under reduced motion. Whether it feels right is a live-QA item.

### Third-party code and licenses

- `flatcap-extensions-list.css`: compared with Awesome-Vivaldi `Extensions.css` (GPL-3.0). It shares the selectors `.extensionIconPopupMenu`, `.extensionIconPopupMenu > .toolbar`, `.ExtensionDropdownIcon > button` and `> button::after`, and several identical declarations (`--popupWidth: 280px`, the flex-column list with `overflow-y: auto`, `overflow-x: hidden`, `flex-wrap: nowrap`, `align-items: stretch`, `justify-content: flex-start`, and the `content: attr(title)` label with ellipsis). That is more than a coincidence of function, so the file is attributed and published under GPL-3.0 (header, README, `LICENSES/GPL-3.0.txt`). **Owner decision before release:** keep it under GPL-3.0, or drop the file and its row to keep the repository purely MIT.
- `flatcap-audio-quiet.css` against Awesome-Vivaldi `Quietify.css` (GPL-3.0), and `flatcap-downloads.css` against `DownloadPanel.css`: different approach and different declarations; the only common thing is the idea and a class name needed to select the same element (`.tab-audio`, `.panel.downloads`). No code copied. The headers keep "inspired by the idea".
- The embedded SVG icons of the author's personal bookmark layout (they look like Font Awesome Free: viewBox 640 and 512, CC BY 4.0, attribution required) are **not published**. The example uses three simple shapes drawn for this repository. See the decision in the README Third-party code.

### Theme id evidence

The CSS is scoped by theme id. The question: does Vivaldi keep the id when a ZIP is imported (or installed from themes.vivaldi.net)? Findings:

1. A Vivaldi export carries an `id`. The Vivaldi forum thread "settings.json file has already been used in another theme" (forum.vivaldi.net/topic/88822) says the store rejects a theme whose `settings.json` id is already used by another theme, and the workaround is to remove the id from the file before uploading. So the id is in the exported file and is what the store uses to tell themes apart.
2. Community themes ship fixed ids per theme: `catppuccin/vivaldi` builds each ZIP with an `id` taken from a `uuid_map.json` (one stable UUID per variant) and tells users to import it with *Open Theme*.
3. Dracula's Vivaldi page says that when you import its ZIP and an earlier version is installed, the Theme Preview popup offers **Update** instead of **Install**. That only works if Vivaldi matches the incoming theme to the installed one by an id read from the file.
4. The Vivaldi help says the ZIP is the JSON parameters plus an optional image and invites editing the parameters by hand.

What was not found: any Vivaldi documentation of the `theme-id-<id>` class on `#browser`, or an explicit statement that an import keeps the id. The evidence points to "kept", but it is indirect. **Not confirmed on a real import.**

Why no id-independent scope was built: the only signals available to CSS are the theme colors Vivaldi exposes as variables on `#browser`, and matching them would need style container queries on exact color strings, which cannot be verified without a running Vivaldi and would break the moment someone nudges a color. If the live check shows that the id changes, the first step is the mechanical scope edit described in [docs/mapping.md](mapping.md#2-scoping-by-theme-id), and the second is to look at what Vivaldi really puts on `#browser` (classes and variables) to pick a signal.

## Part B: live QA in Vivaldi (pending)

Environment to use: a **clean Vivaldi profile**, Vivaldi 8.3.4191.44 on Windows (the version the CSS was written against), then repeat the import check on the newest release available.

Status of each item: `pending`.

### B1. Theme import and the id (do this first: it decides the CSS scope)

| # | Check | Expected | Status |
| :-: | :--- | :--- | :--- |
| 1 | *Settings → Themes → Library → Open Theme* → `Flatcap-Slate.zip` | Live preview, then **Install**; the theme is named **Flatcap Slate**; same for Daylight | pending |
| 2 | Look at the Library after installing both | Two themes, correct names; colors as in the mapping table | pending |
| 3 | Open Vivaldi's UI inspector (it needs the `--debug-packed-apps --silent-debugger-extension-api` launch flags, see the Vivaldi forum) and read the classes of `#browser` with Flatcap Slate active | `theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001` is present; Daylight: `…200002` | pending |
| 4 | Import the same ZIP a second time | The popup offers **Update**, not a duplicate theme | pending |
| 5 | *Export Theme* each theme and diff the exported `settings.json` against the one in the repo | Same `id` and `name`; list every key that differs (the shipped key set is the one Vivaldi 8.3.4191.44 stores; the Catppuccin exports also have `dimBlurred` and `simpleScrollbar`) | pending |
| 6 | Remove a theme, re-import it | Works; CSS applies again | pending |
| 7 | Once the themes are on themes.vivaldi.net, install from there and repeat #3 | The id is the same, or record the new one | pending |

If #3 shows a different id, stop: report it and apply the scope fix before anything else.

### B2. CSS activation (README steps, verbatim)

| # | Check | Status |
| :-: | :--- | :--- |
| 1 | `vivaldi://experiments` shows **Allow for using CSS modifications**; the wording and the restart prompt match the README | pending |
| 2 | *Settings → Appearance → Custom UI Modifications* exists with that name and lets you choose a folder; note the exact button label | pending |
| 3 | With only `flatcap-ui.css` in the folder: address field, bookmark bar, panels and status bar take the Flatcap colors in Slate and in Daylight | pending |
| 4 | Switch to a non-Flatcap theme: no Flatcap CSS applies (no leaks) | pending |
| 5 | Remove the folder, or rename a file to `.css.disabled`, and restart: the file stops applying; the README revert text is accurate | pending |
| 6 | File names without spaces load; a file in a subfolder does not | pending |

### B3. Each layer (Slate and Daylight, mouse and keyboard)

| File | Look at | Status |
| :--- | :--- | :--- |
| `flatcap-ui.css` | Active tab, toolbar button hover, address field border, 2px focus ring on toolbar buttons and fields (Tab key), text selection in a field, `--colorHighlightFg` text on a highlighted fill, no ligatures in a URL with `->` or `==` | pending |
| `flatcap-quick-commands.css` | F2: width (640px, narrow window), 22px input aligned with its hint, selected row bar, URL line, shortcut chip, row heights unchanged while scrolling and typing | pending |
| `flatcap-quick-commands-motion.css` | F2 entry (140ms), typing resizes the list immediately, Esc, quick reopen, reduce motion | pending |
| `flatcap-motion.css` | Button hover feedback on toolbar and bookmark bar, press is immediate, reduce motion | pending |
| `flatcap-surfaces-motion.css` | Popup entry and exit, overlay panel open and close, drag the panel edge (no transition), inactive tab hover, reduce motion | pending |
| `flatcap-tabs-minimal.css` | Tab sizes unchanged, tab stacks, accordion, marked tabs, drop targets, pinned and many tabs | pending |
| `flatcap-url-subtle.css` | Border at rest (decide if it stays in the release: it is below 3:1), hover, focus ring | pending |
| `flatcap-audio-quiet.css` | Playing, muted and Picture in Picture states; no hover zoom; focus ring | pending |
| `flatcap-downloads.css` | Downloads panel and popup: active, completed, failed, selected, unknown size; progress contrast | pending |
| `flatcap-extensions-list.css` | Extensions dropdown as a list: names, badges, scrolling, keyboard, menu near the screen edge | pending |
| `flatcap-extensions-inline.css` | Expanding the extensions group: raised surface, 140ms icon entry, collapse | pending |

### B4. Accessibility and OS settings

| Check | Status |
| :--- | :--- |
| Reduce motion on (Windows *Animation effects* off): no layer animates | pending |
| Windows contrast themes (forced colors): the system palette wins, nothing unreadable | pending |
| Windows *Increase contrast* / `prefers-contrast: more`: the base switches to the high-contrast text and border colors | pending |
| Keyboard only: every control the CSS touches shows a visible focus | pending |

### B5. Example

| Check | Status |
| :--- | :--- |
| `examples/bookmark-bar-inline.css` adapted to a few folder titles: layout at 900px and wider, fallback below 900px, Downloads button anchor, icons follow the theme in Slate and Daylight, hover | pending |

### B6. Screenshots (for the README; take them in the live QA)

Save in `images/` with these names (the README links them): `screenshot-slate.png`, `screenshot-daylight.png`, `quick-commands-slate.png`, `quick-commands-daylight.png`. Use a clean profile with no personal bookmarks, history, search engines or tabs, and credit any artwork shown. Until they exist, the README images are broken links.

### B7. Release gates still open

- Owner decision on the GPL-3.0 file (see Part A).
- Decision on `flatcap-url-subtle.css` (kept as a documented exception, or fixed or removed).
- After B1 to B6, replace "not tested" in the README Compatibility section with what was verified.
- Publish on themes.vivaldi.net (separate step; the README has an HTML TODO comment for the link).
