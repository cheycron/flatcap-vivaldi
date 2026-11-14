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
| File | forced-colors guard | reduced-motion guard | `transition: all` | Transitions a layout property | Selectors outside the theme-id scope | `font-size` values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `flatcap-ui.css` | yes | n/a | no | no | none | (none set) |
| `flatcap-quick-commands.css` | yes | n/a | no | no | none | 13px, 22px |
| `flatcap-quick-commands-motion.css` | yes | yes | no | no | none | (none set) |
| `flatcap-motion.css` | yes | yes | no | no | none | (none set) |
| `flatcap-surfaces-motion.css` | yes | yes | no | yes (retimed native panel width, not while dragging) | none | (none set) |
| `flatcap-tabs-minimal.css` | yes | n/a | no | no | none | (none set) |
| `flatcap-url-subtle.css` | yes | n/a | no | no | none | (none set) |
| `flatcap-audio-quiet.css` | yes | n/a | no | no | none | (none set) |
| `flatcap-downloads.css` | yes | n/a | no | no | none | (none set) |
| `flatcap-extensions-list.css` | yes | n/a | no | no | none | 13px |
| `flatcap-extensions-inline.css` | yes | yes | no | no | none | (none set) |
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

Status values: `PASS` (observed live), `PARTIAL` (part of the check was observed; the text says which part), `NOT TESTED`. A DOM or computed-style reading proves the CSS is loaded and that a property has the expected value; it does not prove the screen looks right. Only the screenshots in B6 were looked at by eye; the other rows are not visual checks.

### B1. Theme import and the id

| # | Check | Result | Status |
| :-: | :--- | :--- | :--- |
| 1 | *Open Theme* with each ZIP | Both ZIPs were imported and installed in the throw-away profile. | PASS |
| 2 | Library after installing both | Two themes, **Flatcap Slate** and **Flatcap Daylight**. The stored `colorBg`, `colorFg`, `colorHighlightBg`, `colorAccentBg`, `colorWindowBg` match the ZIPs (see #5 for the exceptions). | PASS |
| 3 | Classes of `#browser` | With Slate active: `theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001`. With Daylight active: `theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200002`. **The import keeps the id**, so the theme-id scope works. Read through the remote-debugging port, not the `--debug-packed-apps` flags. | PASS |
| 4 | Import the same ZIP again | The popup offered **Update**; after accepting there were still two user themes, no duplicate. | PASS |
| 5 | Diff against an export | No Export dialog was driven. First pass (before Q4): `defaultBackground` differed (ZIP: canvas; stored: surface), so the ZIPs now carry `bg.surface` (`#20252B` / `#FAFBFC`). Q4 re-import of the current ZIPs (Slate preview object read from `vivaldi.themes.preview`): `defaultBackground` is kept as `#20252B`; Vivaldi adds `dimBlurred: false` and `simpleScrollbar: false`. Those two keys are the only known differences; the Daylight preview object was not diffed again, and a real Export was not compared. | PARTIAL |
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
| `flatcap-quick-commands.css` | F2 opened the popup. Slate: width 640px, background `rgb(41, 47, 54)` (`#292F36`), text `rgb(213, 219, 227)` (`#D5DBE3`), search input 22px. Daylight: width 640px, background `rgb(255, 255, 255)`, text `rgb(40, 49, 59)` (`#28313B`), search input 22px. Esc closed it. Q4 re-check with the 13px layer: section header 13px, shadow token `--fc-shadow-overlay` resolved to the core elevation (Slate `rgba(0,0,0,.24) 0 8px 24px`); the shortcut chip size was not read. Narrow window, selected row bar, URL line, shortcut chip and row heights: not checked. | PARTIAL |
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

The four PNGs the README links are in `images/`, 1440 × 900 each. They were retaken in the Q4 remediation with the current ZIPs and CSS (an earlier set was replaced; a provisional Q4 Slate take was discarded because a Theme Preview dialog was in the shot).

Method:

- A new throw-away profile (`Flatcap-Q4-20261114` in the Windows temp folder, Vivaldi 8.3.4191.44, high remote-debugging port, viewport 1440 × 900), separate from the author's running Vivaldi, which was not touched.
- Themes: both current ZIPs were imported with `vivaldi.themePrivate.import` (the call behind *Open Theme*); the preview objects were copied to the user theme list through the profile preferences. This is **not** a click on the *Install* button. The `css/` files from the repo (hashes matched on both ends) were loaded as UI mods. `--fc-*` tokens and the `theme-id-…` class were read before each capture (Slate `--fc-bg-canvas` `#191D22`, Daylight `#F3F5F7`).
- Content: three tabs on public pages (`iana.org/help/example-domains`, `example.org`, `example.com`), no logged-in account. The page color scheme was not emulated this time.
- Capture: `Page.captureScreenshot`. Before each capture the script checked that no `.modal-wrapper` dialog and no Quick Commands popup was open. For the popup shots F2 was pressed and `tab` typed; Esc (`keyDown`) closed it, and its closure was checked.
- Quick Commands values read in the same run: width 640px, section header 13px, search input 22px, search value `tab`. Slate shadow `rgb(61, 70, 82) 0 0 0 1px, rgba(0, 0, 0, 0.24) 0 8px 24px 0`; Daylight `rgb(210, 217, 224) 0 0 0 1px, rgba(25, 29, 34, 0.1) 0 8px 24px 0`. The `.quick-command-shortcut` element was not present with the computed size read (null), so the 13px floor was **not** observed for the shortcut chip.
- Transfer: bytes were posted to a temporary receiver; the SHA-256 on the receiving side equals the one computed on the test machine.
- Review: each PNG was opened and looked at. No dialog, no personal data, no other windows. Slate is a dark window, Daylight a light one, and the popup shows `tab` with its results. Vivaldi's default side-panel icons and the status bar clock are visible. The example.com page looks dark under Slate and light under Daylight; why (Vivaldi's website color scheme setting) was not investigated.

| File | Size | Bytes | SHA-256 |
| :--- | :--- | ---: | :--- |
| `screenshot-slate.png` | 1440 × 900 | 73154 | `BBF43BDD1F774907151818E14FD1B2C7AA4E70A39E5606C5936008950BBE12FF` |
| `screenshot-daylight.png` | 1440 × 900 | 71143 | `B87793679D6AE80675B243F253B6C0FE23E180ECD16B96F56D6FF33669C59723` |
| `quick-commands-slate.png` | 1440 × 900 | 66909 | `8A1C4DA8CC367BC1B3A24764CA0E739D6B052B44F7A9C69725EC1B33D20B136B` |
| `quick-commands-daylight.png` | 1440 × 900 | 66122 | `E1D41CB4FA62EA9C976F9EEDAF7B1022107E1B38F1C22FF3DCC4BDBD88FD34FD` |

The Q4 profile and temporary files are removed after the run; the protected pre-existing folder was not touched.

### B7. Release gates still open

- Owner decision on the GPL-3.0 file (see Part A).
- Decision on `flatcap-url-subtle.css` (kept as a documented exception, or fixed or removed).
- Finish B3 to B5 (the layers marked NOT TESTED, accessibility, the example). Screenshots (B6) retaken in Q4 for Slate and Daylight.
- Publish on themes.vivaldi.net (separate step; the README has an HTML TODO comment for the link).
