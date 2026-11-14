# QA report: Flatcap 2.0 for Vivaldi

Two parts. **Part A** is the build check: it runs without Vivaldi, on every push (`.github/workflows/validate.yml`), and its result is reproduced below. **Part B** is the live QA in a real Vivaldi 8.3.4191.44: **partial**. Imports, the theme id, the base layer and the Quick Commands layer were checked; most of the other layers were only confirmed to load. Part B says item by item what was and was not checked.

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

What was not found: any Vivaldi documentation of the `theme-id-<id>` class on `#browser`, or an explicit statement that an import keeps the id. The evidence pointed to "kept", but it was indirect. **Confirmed on a real import in the live QA (Part B1 #3): the ids are kept.**

Why no id-independent scope was built: the only signals available to CSS are the theme colors Vivaldi exposes as variables on `#browser`, and matching them would need style container queries on exact color strings, which cannot be verified without a running Vivaldi and would break the moment someone nudges a color. If a future Vivaldi changes the id on import, the first step is the mechanical scope edit described in [docs/mapping.md](mapping.md#2-scoping-by-theme-id), and the second is to look at what Vivaldi really puts on `#browser` (classes and variables) to pick a signal.

## Part B: live QA in Vivaldi (partial)

Run on 2026-11-14 on Windows, Vivaldi **8.3.4191.44**, in a **throw-away profile** (`--user-data-dir` in the Windows temp folder, `--lang=en-US`, the UI driven through Chrome DevTools Protocol on `127.0.0.1`). The author's real profile and CSS folder were not used. The profile and the temporary files were deleted afterwards.

Status values: `PASS` (observed live), `PARTIAL` (part of the check was observed; the text says which part), `NOT TESTED`. A DOM or computed-style reading proves the CSS is loaded and that a property has the expected value; it does not prove the screen looks right. No screenshot was inspected by eye in this run (see B6).

### B1. Theme import and the id

| # | Check | Result | Status |
| :-: | :--- | :--- | :--- |
| 1 | *Open Theme* with each ZIP | Both ZIPs were imported and installed in the throw-away profile. | PASS |
| 2 | Library after installing both | Two themes, **Flatcap Slate** and **Flatcap Daylight**. The stored `colorBg`, `colorFg`, `colorHighlightBg`, `colorAccentBg`, `colorWindowBg` match the ZIPs (see #5 for the exceptions). | PASS |
| 3 | Classes of `#browser` | With Slate active: `theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001`. With Daylight active: `theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200002`. **The import keeps the id**, so the theme-id scope works. Read through the remote-debugging port, not the `--debug-packed-apps` flags. | PASS |
| 4 | Import the same ZIP again | The popup offered **Update**; after accepting there were still two user themes, no duplicate. | PASS |
| 5 | Diff against an export | No Export dialog was driven. Instead the ZIP `settings.json` was diffed against the theme object Vivaldi stored in `Preferences`. `id` and `name` are equal. Three keys differ, for both themes: `defaultBackground` (ZIP: the canvas color, `#191D22` / `#F3F5F7`; stored: the surface color, `#20252B` / `#FAFBFC`), `dimBlurred` (absent in the ZIP, stored `false`) and `simpleScrollbar` (absent in the ZIP, stored `false`). The ZIPs were not changed: the visible window color comes from `colorWindowBg`, which is unchanged. | PARTIAL |
| 6 | Remove a theme, re-import it | Not run. | NOT TESTED |
| 7 | Install from themes.vivaldi.net | Not published yet. | NOT TESTED |

Finding (theme schedule): a new profile has *Settings → Themes → Schedule* set to **Operating System**. While it is, the theme assigned to the current OS mode (here dark) wins: setting `vivaldi.themes.current` had no visible effect until the schedule was switched to **No Schedule**. This is documented in the README.

### B2. CSS activation

| # | Check | Result | Status |
| :-: | :--- | :--- | :--- |
| 1 | The experiment | `vivaldi://experiments` opens `chrome://flags/`. The entry is named **Allow CSS modifications** (`#vivaldi-css-mods`), default state `Default`. The README said "Allow for using CSS modifications"; it now uses the real name. It was enabled in the throw-away profile (`Local State` lists `vivaldi-css-mods@1`). The restart prompt was not recorded. | PARTIAL |
| 2 | *Settings → Appearance → Custom UI Modifications* | The section exists with that heading. The folder was set through the preference `vivaldi.appearance.css_ui_mods_directory`; the native folder dialog was not driven, so the button label was not recorded. | PARTIAL |
| 3 | Only `flatcap-ui.css` in the folder | After a restart the `--fc-*` tokens resolved on `#browser`: Slate `--fc-bg-canvas #191D22`, `--fc-bg-surface #20252B`, `--fc-accent-fg #9BBFDF`; Daylight `#F3F5F7`, `#FAFBFC`, `#285D85`. Window background `rgb(25, 29, 34)` in Slate and `rgb(243, 245, 247)` in Daylight. Whether the address field, bookmark bar, panels and status bar look right was not checked by eye. | PARTIAL |
| 4 | Non-Flatcap theme | With Vivaldi's built-in **Dark** (`theme-id-Vivaldi2`) and **Vivaldi** (`theme-id-Vivaldi1`) the `--fc-*` tokens were empty and the window kept Vivaldi's own background (`rgb(46, 47, 55)` and `rgb(245, 245, 245)`). Only the tokens were read; other properties were not. | PARTIAL |
| 5 | Remove the folder or `.css.disabled` | Not run. | NOT TESTED |
| 6 | File names and subfolders | The 11 files of `css/`, with their repo hashes, placed directly in the folder were loaded as 11 imports, each with rules. A subfolder was not tried. **Finding:** choosing the folder while Vivaldi is running does not apply it: the stylesheet was empty until Vivaldi was restarted (the README already asks for the restart). | PARTIAL |

### B3. Each layer

| File | Result | Status |
| :--- | :--- | :--- |
| `flatcap-ui.css` | Tokens and window background as in B2 #3. Hover, address field border, focus rings, text selection, ligatures: not checked. | PARTIAL |
| `flatcap-quick-commands.css` | F2 opened the popup. Slate: width 640px, background `rgb(41, 47, 54)` (`#292F36`), text `rgb(213, 219, 227)` (`#D5DBE3`), search input 22px. Daylight: width 640px, background `rgb(255, 255, 255)`, text `rgb(40, 49, 59)` (`#28313B`), search input 22px. Esc closed it. Narrow window, selected row bar, URL line, shortcut chip and row heights: not checked. | PARTIAL |
| `flatcap-quick-commands-motion.css` | Loaded (4 rules). The 140ms entry and the rest: not checked. | NOT TESTED |
| `flatcap-motion.css` | Loaded (2 rules). Behavior not checked. | NOT TESTED |
| `flatcap-surfaces-motion.css` | Loaded (2 rules). Behavior not checked. | NOT TESTED |
| `flatcap-tabs-minimal.css` | Loaded (1 rule). Behavior not checked. | NOT TESTED |
| `flatcap-url-subtle.css` | Loaded (1 rule). Border, hover and the 3:1 decision not checked. | NOT TESTED |
| `flatcap-audio-quiet.css` | Loaded (1 rule). No audio or Picture in Picture state was tried. | NOT TESTED |
| `flatcap-downloads.css` | Loaded (1 rule). No download was made. | NOT TESTED |
| `flatcap-extensions-list.css` | Loaded (7 rules). No extensions in the profile. | NOT TESTED |
| `flatcap-extensions-inline.css` | Loaded (3 rules). No extensions in the profile. | NOT TESTED |

### B4. Accessibility and OS settings

| Check | Status |
| :--- | :--- |
| Reduce motion on: no layer animates | NOT TESTED |
| Windows contrast themes (forced colors) | NOT TESTED |
| *Increase contrast* / `prefers-contrast: more` | NOT TESTED |
| Keyboard only: visible focus on every touched control | NOT TESTED |

### B5. Example

| Check | Result | Status |
| :--- | :--- | :--- |
| `examples/bookmark-bar-inline.css` | The file hash matches the repo. It parses as a stylesheet (10 top-level rules, 22 opening braces) in the Vivaldi UI. It was not applied: the throw-away profile has no bookmark bar or folders to adapt it to. | NOT TESTED |

### B6. Screenshots

The four PNGs the README links were captured on the test machine with `Page.captureScreenshot` of the Vivaldi window (Slate and Daylight, with and without the Quick Commands popup). They are **not in `images/`**: the tool channel returns text only, so they could not be copied into the repo, and nobody looked at them, so they are not committed. They were kept on the Windows machine in the shared `Public` folder, in a folder named `flatcap-vivaldi-qa-shots` (SHA-256 below) for the owner to inspect and copy. Until they are in `images/`, the README images are broken links.

| File | Bytes | SHA-256 |
| :--- | ---: | :--- |
| `screenshot-slate.png` | 74518 | `772DF2E8D171AC2EACB027D6754F6BD08AACD16435A284CC00E0E4011F358F73` |
| `screenshot-daylight.png` | 72760 | `23603AE3CE95D583D2D78109E141F3BD3FB4F54BBFE50499FF64F824B4FCD26D` |
| `quick-commands-slate.png` | 79261 | `6C06A655BAC6BE339341A7001C1DB56A34B2A433111E05F0D02DCEF593B5FEB3` |
| `quick-commands-daylight.png` | 77058 | `221886D7DE707A40B09D2C392A686F404F1F81FF3174BCEFA004148707118532` |

The tab shown is `https://example.com/` in an otherwise empty profile. Check that the capture includes the page area and not only the toolbar before using it.

### B7. Release gates still open

- Owner decision on the GPL-3.0 file (see Part A).
- Decision on `flatcap-url-subtle.css` (kept as a documented exception, or fixed or removed).
- Finish B3 to B6 (the layers marked NOT TESTED, accessibility, the example) and put the four screenshots in `images/` (B6).
- Publish on themes.vivaldi.net (separate step; the README has an HTML TODO comment for the link).
