# Mapping: Flatcap 2.0 core to Vivaldi

Every value comes from `src/theme.json`, a **manual copy** of the Flatcap 2.0 core (`cheycron/flatcap-theme`, `src/theme.json`; byte-identical on 2026-11-14, nothing checks that afterwards, see the README, *Contributing*). Nothing is invented for this port: the one token the port adds on its own account, `--fc-shadow-overlay`, is the core's `elevation.<theme>.shadow.overlay`. `scripts/build.py --sync` writes the theme ZIPs and `css/flatcap-ui.css` from it; `--check` fails if any of them is stale.

Vivaldi has two places to put color:

1. **The theme** (the ZIP, a `settings.json` of theme parameters). Five colors, a few switches. This is native, supported and survives Vivaldi updates.
2. **The interface CSS** (*Custom UI Modifications*, optional). Tokens (`--fc-*`) and rules for the parts the theme editor cannot reach. Unofficial.

## 1. Theme parameters

Format of the ZIP: the one Vivaldi writes with **Settings → Themes → Library → Export Theme** and reads with **Open Theme**: a ZIP with `settings.json` at its root and, when the theme has a background image, the image next to it. These themes have no image. See [Sources](#sources).

<!-- build:params -->
| `settings.json` key | Flatcap role | Slate | Daylight |
| :--- | :--- | :--- | :--- |
| `colorBg` | `bg.surface` | `#20252B` | `#FAFBFC` |
| `colorFg` | `text.primary` | `#D5DBE3` | `#28313B` |
| `colorHighlightBg` | `accent.fill` | `#9BBFDF` | `#285D85` |
| `colorAccentBg` | `bg.canvas` | `#191D22` | `#F3F5F7` |
| `colorWindowBg` | `bg.canvas` | `#191D22` | `#F3F5F7` |
| `defaultBackground` | `bg.surface` | `#20252B` | `#FAFBFC` |
| `accentSaturationLimit` | (theme setting) | `0.75` | `0.85` |
| `id` | (theme identity, see Scoping) | `77d85a94-0f14-4fe6-88b6-2fcf00200001` | `77d85a94-0f14-4fe6-88b6-2fcf00200002` |
| `name` | (visible name) | Flatcap Slate | Flatcap Daylight |

Fixed parameters (the same in both themes): `accentFromPage`: `false`, `accentOnWindow`: `false`, `alpha`: `1`, `backgroundImage`: `""`, `backgroundPosition`: `"stretch"`, `backgroundSource`: `""`, `blur`: `0`, `colorPosition`: `"unified"`, `contrast`: `0`, `engineVersion`: `1`, `preferSystemAccent`: `false`, `radius`: `4`, `transparencyTabBar`: `false`, `transparencyTabs`: `false`, `url`: `""`, `version`: `1`.
<!-- /build:params -->

How the five colors are used, in Vivaldi's *Unified* coloring mode (`colorPosition: unified`): `colorWindowBg` and `colorAccentBg` paint the window and the tab bar (`bg.canvas`), `colorBg` paints the toolbars and panels (`bg.surface`), `colorFg` is the text color, `colorHighlightBg` is the accent (selection, focus, active fills). Vivaldi chooses the text color on highlighted fills itself; the base CSS replaces it with `accent.on` (see below). `accentFromPage`, `preferSystemAccent` and `accentOnWindow` are off, so the page does not recolor the browser. `radius: 4` is `radius.control` (0.25rem) in pixels.

`defaultBackground` is `bg.surface`, the same value `colorBg` has: that is what Vivaldi 8.3.4191.44 stored for it after importing the earlier ZIPs (which had `bg.canvas` there), so the ZIP now ships what Vivaldi would keep. It was not re-imported to confirm (see the QA report, B1 #5). Vivaldi also adds `dimBlurred` and `simpleScrollbar`, both `false`; the ZIPs leave them out.

The two ZIPs are deterministic in content and metadata: `settings.json` is written with sorted keys and two-space indent, the ZIP member has a fixed timestamp, Unix attributes, deflate compression and a fixed order, and `--check` compares each of those fields. The deflate stream itself depends on the zlib of the building Python, so another zlib can give different compressed bytes for the same content (a note, not an error).

<!-- build:zipcheck -->
| ZIP | Members | `id` | `name` | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
| `themes/Flatcap-Slate.zip` | `settings.json` | `77d85a94-0f14-4fe6-88b6-2fcf00200001` | Flatcap Slate | 2026-01-01 (fixed) |
| `themes/Flatcap-Daylight.zip` | `settings.json` | `77d85a94-0f14-4fe6-88b6-2fcf00200002` | Flatcap Daylight | 2026-01-01 (fixed) |
<!-- /build:zipcheck -->

## 2. Scoping by theme id

<!-- build:scope -->
`#browser:is(.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001,.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200002)`, that is `#browser.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200001` (Slate) and `#browser.theme-id-77d85a94-0f14-4fe6-88b6-2fcf00200002` (Daylight).
<!-- /build:scope -->

Every CSS rule starts with that selector (or with one of its two halves), so the CSS applies only while one of the two Flatcap themes is active. With any other theme, or with the CSS files loaded but the theme changed, nothing is styled and nothing leaks.

The scope relies on two facts:

- **The theme keeps its id when you import the ZIP.** The ids are fixed in `src/vivaldi.json`, and each `settings.json` carries its own. The forum and community evidence was indirect (see the [QA report](qa-report.md#theme-id-evidence)); a real import in Vivaldi 8.3.4191.44 kept both ids (QA report B1 #3).
- **Vivaldi puts the theme id on `#browser` as a `theme-id-<id>` class.** This was observed in Vivaldi 8.3.4191.44 (QA report B1 #3) and is not documented by Vivaldi.

If the import ever assigns a new id, the CSS files stop applying. Changing the scope is then a mechanical edit: the scope is built in one function (`scope_all` in `scripts/build.py`) and every hand-written layer uses the same `#browser:is(.theme-id-…,.theme-id-…)` prefix. `--check` parses every file in `css/` and fails on any selector (inside `@media` and `@supports` too) that does not start with the scope, and on any id that is not one of the two shipped ids. `@keyframes` have no selector to scope. **`examples/` is exempt on purpose**: `examples/bookmark-bar-inline.css` is not scoped by theme id and applies under any theme; the check requires its header to say so. An alternative scope that does not depend on the id has not been built because it has no reliable signal to key on (see the QA report).

## 3. What the base CSS paints

`css/flatcap-ui.css` defines every `--fc-*` token for each theme (colors, typography, metrics and the overlay shadow: 79 per theme) on `#browser.theme-id-…`, sets `font-family` to `--fc-font-ui`, and adds these rules (not applied in forced-colors mode):

<!-- build:rules -->
| Selector (after the scope) | Property | Token | Role |
| :--- | :--- | :--- | :--- |
| `:is(.toolbar-mainbar,.bookmark-bar,#panels-container,.toolbar-statusbar)` | `background-color` | `var(--fc-bg-surface)` | `bg.surface` |
| `:is(.toolbar-mainbar,.bookmark-bar,#panels-container,.toolbar-statusbar)` | `color` | `var(--fc-text-primary)` | `text.primary` |
| `:is(.UrlBar-AddressField,.SearchField)` | `background-color` | `var(--fc-bg-canvas)` | `bg.canvas` |
| `:is(.UrlBar-AddressField,.SearchField)` | `color` | `var(--fc-text-primary)` | `text.primary` |
| `:is(.UrlBar-AddressField,.SearchField)` | `border` | `1px solid var(--fc-border-control)` | `border.control` |
| `:is(.UrlBar-AddressField,.SearchField)` | `border-radius` | `var(--fc-radius-control)` | (metric) |
| `.tab-position .tab.active` | `background-color` | `var(--fc-bg-selected)` | `bg.selected` |
| `.tab-position .tab.active` | `color` | `var(--fc-text-primary)` | `text.primary` |
| `.tab-position .tab.active` | `text-decoration` | `none` | (metric) |
| `.toolbar-mainbar .button-toolbar button:not(:disabled):hover` | `background-color` | `var(--fc-bg-hover)` | `bg.hover` |
| `.toolbar-mainbar .button-toolbar button:not(:disabled):hover` | `color` | `var(--fc-text-primary)` | `text.primary` |
| `:is(button,input,select,textarea,[tabindex]):not(.UrlBar-AddressField input):focus-visible` | `outline` | `var(--fc-focus-width) solid var(--fc-focus-ring)` | `focus.width`, `focus.ring` |
| `:is(button,input,select,textarea,[tabindex]):not(.UrlBar-AddressField input):focus-visible` | `outline-offset` | `var(--fc-focus-offset)` | `focus.offset` |
| `.UrlBar-AddressField:focus-within` | `outline` | `var(--fc-focus-width) solid var(--fc-focus-ring)` | `focus.width`, `focus.ring` |
| `.UrlBar-AddressField:focus-within` | `outline-offset` | `calc(var(--fc-focus-width) * -1)` | `focus.width` |
| `:is(input,textarea)::selection` | `background` | `var(--fc-selection-bg)` | `selection.bg` |
| `:is(input,textarea)::selection` | `color` | `var(--fc-selection-fg)` | `selection.fg` |
| `.UrlBar-AddressField input` | `font-variant-ligatures`, `font-feature-settings` | `none`, `normal` | (no ligatures in URLs) |
| scope | `--colorHighlightFg` (`!important`) | `var(--fc-accent-on)` | `accent.on` |
<!-- /build:rules -->

Load order: no rule of one layer depends on being read before or after another. Where a layer restyles what the base also styles, the layer's selector has the higher specificity (`flatcap-url-subtle.css` repeats `.UrlBar-AddressField`, `flatcap-extensions-list.css` repeats `.extensionIconPopupMenu` on its focus rule), and `--check` fails if two files set the same property of the same element at equal specificity with different values.

Under `prefers-contrast: more`, `text.primary`, `text.secondary`, `text.muted` and `border.control` switch to the core's `contrast.*` set.

## 4. Tokens used by the optional files

<!-- build:tokens -->
| File | Tokens used |
| :--- | :--- |
| `flatcap-quick-commands.css` | `--fc-bg-hover`, `--fc-bg-raised`, `--fc-bg-selected`, `--fc-bg-surface`, `--fc-border-subtle`, `--fc-focus-ring`, `--fc-font-ui`, `--fc-radius-dialog`, `--fc-shadow-overlay`, `--fc-text-primary`, `--fc-text-secondary` |
| `flatcap-quick-commands-motion.css` | (none) |
| `flatcap-motion.css` | `--fc-motion-fast` |
| `flatcap-surfaces-motion.css` | (none) |
| `flatcap-tabs-minimal.css` | `--fc-bg-hover`, `--fc-bg-raised`, `--fc-text-primary`, `--fc-text-secondary` |
| `flatcap-url-subtle.css` | `--fc-border-control`, `--fc-border-subtle`, `--fc-focus-ring` |
| `flatcap-audio-quiet.css` | `--fc-bg-hover`, `--fc-focus-ring`, `--fc-radius-control` |
| `flatcap-downloads.css` | `--fc-accent-fill`, `--fc-bg-hover`, `--fc-bg-surface`, `--fc-border-subtle`, `--fc-text-primary` |
| `flatcap-extensions-list.css` | `--fc-bg-hover`, `--fc-bg-raised`, `--fc-focus-ring`, `--fc-font-ui`, `--fc-radius-panel`, `--fc-text-primary` |
| `flatcap-extensions-inline.css` | `--fc-bg-hover`, `--fc-bg-raised`, `--fc-border-subtle` |
<!-- /build:tokens -->

## 5. Contrast

Measured on the exact values in `src/theme.json` (WCAG 2.x, sRGB). Targets are the contracts of the Flatcap core: 7:1 primary text, 5:1 informative text, 3:1 functional outlines and focus, 4.5:1 text on fills. A row marked *report only* is shown, not enforced.

<!-- build:contrast -->
| Theme | Pair | Ratio | Target | Result |
| :--- | :--- | ---: | ---: | :--- |
| slate | text.primary on bg.canvas (window, tab bar, address and search fields) `#D5DBE3` / `#191D22` | 12.15 | 7 | pass |
| slate | text.primary on bg.surface (toolbars, bookmark bar, panels, status bar) `#D5DBE3` / `#20252B` | 11.07 | 7 | pass |
| slate | text.primary on bg.raised (Quick Commands, expanded extensions group, active tab (minimal tabs)) `#D5DBE3` / `#292F36` | 9.70 | 7 | pass |
| slate | text.primary on bg.hover (toolbar button hover, hovered tab, extension toggle) `#D5DBE3` / `#323A43` | 8.27 | 7 | pass |
| slate | text.primary on bg.selected (active tab, selected Quick Command row) `#D5DBE3` / `#263E53` | 7.95 | 7 | pass |
| slate | text.secondary on bg.canvas (inactive tab on the tab bar) `#AEB8C4` / `#191D22` | 8.43 | 5 | pass |
| slate | text.secondary on bg.surface (section headers, shortcut chips, inactive tab) `#AEB8C4` / `#20252B` | 7.68 | 5 | pass |
| slate | text.secondary on bg.raised (Quick Commands URL line) `#AEB8C4` / `#292F36` | 6.73 | 5 | pass |
| slate | text.secondary on bg.hover (hovered Quick Commands row) `#AEB8C4` / `#323A43` | 5.74 | 5 | pass |
| slate | text.secondary on bg.selected (URL line of the selected Quick Command) `#AEB8C4` / `#263E53` | 5.51 | 5 | pass |
| slate | text.primary at 85% on bg.surface (download file size) `#D5DBE3` / `#20252B` | 8.40 | 5 | pass |
| slate | text.primary at 85% on bg.hover (hovered download row) `#D5DBE3` / `#323A43` | 6.48 | 5 | pass |
| slate | accent.on on accent.fill (text on highlighted fills, --colorHighlightFg) `#101820` / `#9BBFDF` | 9.30 | 4.5 | pass |
| slate | selection.fg on selection.bg (selected text in fields) `#D5DBE3` / `#3C546B` | 5.64 | 4.5 | pass |
| slate | focus.ring on bg.canvas (2px focus ring, selected-row bar, address field focus) `#B0D2F0` / `#191D22` | 10.74 | 3 | pass |
| slate | focus.ring on bg.surface (2px focus ring, selected-row bar, address field focus) `#B0D2F0` / `#20252B` | 9.79 | 3 | pass |
| slate | focus.ring on bg.raised (2px focus ring, selected-row bar, address field focus) `#B0D2F0` / `#292F36` | 8.57 | 3 | pass |
| slate | focus.ring on bg.hover (2px focus ring, selected-row bar, address field focus) `#B0D2F0` / `#323A43` | 7.31 | 3 | pass |
| slate | focus.ring on bg.selected (2px focus ring, selected-row bar, address field focus) `#B0D2F0` / `#263E53` | 7.03 | 3 | pass |
| slate | border.control on bg.canvas (address and search field border, field fill) `#8593A5` / `#191D22` | 5.41 | 3 | pass |
| slate | border.control on bg.surface (address and search field border, bar) `#8593A5` / `#20252B` | 4.93 | 3 | pass |
| slate | accent.fill on border.subtle (download progress fill vs its track) `#9BBFDF` / `#3D4652` | 4.97 | 3 | pass |
| slate | accent.fill on bg.surface (download progress fill vs panel) `#9BBFDF` / `#20252B` | 8.02 | 3 | pass |
| slate | border.subtle on bg.canvas (address field at rest with flatcap-url-subtle.css, report only) `#3D4652` / `#191D22` | 1.77 | - | report only |
| slate | border.subtle on bg.surface (address field at rest with flatcap-url-subtle.css, report only) `#3D4652` / `#20252B` | 1.61 | - | report only |
| slate | bg.canvas on bg.surface (address field fill vs bar, report only) `#191D22` / `#20252B` | 1.10 | - | report only |
| daylight | text.primary on bg.canvas (window, tab bar, address and search fields) `#28313B` / `#F3F5F7` | 12.06 | 7 | pass |
| daylight | text.primary on bg.surface (toolbars, bookmark bar, panels, status bar) `#28313B` / `#FAFBFC` | 12.73 | 7 | pass |
| daylight | text.primary on bg.raised (Quick Commands, expanded extensions group, active tab (minimal tabs)) `#28313B` / `#FFFFFF` | 13.19 | 7 | pass |
| daylight | text.primary on bg.hover (toolbar button hover, hovered tab, extension toggle) `#28313B` / `#E6EBF0` | 10.99 | 7 | pass |
| daylight | text.primary on bg.selected (active tab, selected Quick Command row) `#28313B` / `#DCE9F4` | 10.68 | 7 | pass |
| daylight | text.secondary on bg.canvas (inactive tab on the tab bar) `#465463` / `#F3F5F7` | 7.09 | 5 | pass |
| daylight | text.secondary on bg.surface (section headers, shortcut chips, inactive tab) `#465463` / `#FAFBFC` | 7.48 | 5 | pass |
| daylight | text.secondary on bg.raised (Quick Commands URL line) `#465463` / `#FFFFFF` | 7.75 | 5 | pass |
| daylight | text.secondary on bg.hover (hovered Quick Commands row) `#465463` / `#E6EBF0` | 6.46 | 5 | pass |
| daylight | text.secondary on bg.selected (URL line of the selected Quick Command) `#465463` / `#DCE9F4` | 6.28 | 5 | pass |
| daylight | text.primary at 85% on bg.surface (download file size) `#28313B` / `#FAFBFC` | 7.98 | 5 | pass |
| daylight | text.primary at 85% on bg.hover (hovered download row) `#28313B` / `#E6EBF0` | 7.17 | 5 | pass |
| daylight | accent.on on accent.fill (text on highlighted fills, --colorHighlightFg) `#FAFBFC` / `#285D85` | 6.77 | 4.5 | pass |
| daylight | selection.fg on selection.bg (selected text in fields) `#28313B` / `#C8DDF0` | 9.45 | 4.5 | pass |
| daylight | focus.ring on bg.canvas (2px focus ring, selected-row bar, address field focus) `#285D85` / `#F3F5F7` | 6.42 | 3 | pass |
| daylight | focus.ring on bg.surface (2px focus ring, selected-row bar, address field focus) `#285D85` / `#FAFBFC` | 6.77 | 3 | pass |
| daylight | focus.ring on bg.raised (2px focus ring, selected-row bar, address field focus) `#285D85` / `#FFFFFF` | 7.01 | 3 | pass |
| daylight | focus.ring on bg.hover (2px focus ring, selected-row bar, address field focus) `#285D85` / `#E6EBF0` | 5.85 | 3 | pass |
| daylight | focus.ring on bg.selected (2px focus ring, selected-row bar, address field focus) `#285D85` / `#DCE9F4` | 5.68 | 3 | pass |
| daylight | border.control on bg.canvas (address and search field border, field fill) `#6C7A89` / `#F3F5F7` | 4.02 | 3 | pass |
| daylight | border.control on bg.surface (address and search field border, bar) `#6C7A89` / `#FAFBFC` | 4.24 | 3 | pass |
| daylight | accent.fill on border.subtle (download progress fill vs its track) `#285D85` / `#D2D9E0` | 4.92 | 3 | pass |
| daylight | accent.fill on bg.surface (download progress fill vs panel) `#285D85` / `#FAFBFC` | 6.77 | 3 | pass |
| daylight | border.subtle on bg.canvas (address field at rest with flatcap-url-subtle.css, report only) `#D2D9E0` / `#F3F5F7` | 1.30 | - | report only |
| daylight | border.subtle on bg.surface (address field at rest with flatcap-url-subtle.css, report only) `#D2D9E0` / `#FAFBFC` | 1.37 | - | report only |
| daylight | bg.canvas on bg.surface (address field fill vs bar, report only) `#F3F5F7` / `#FAFBFC` | 1.05 | - | report only |
<!-- /build:contrast -->

The `flatcap-url-subtle.css` rows are the **explicit accessibility exception**: the address field border in `border.subtle` at rest is far below 3:1 against both the field fill and the bar. The only core border token that reaches 3:1 is `border.control`, which is the base look already, so a compliant version of the layer would do nothing. It is a deliberate quiet look in an optional layer, documented in the README Accessibility section.

## Sources

- Vivaldi Help, [Shareable Vivaldi Themes](https://help.vivaldi.com/desktop/appearance-customization/shareable-vivaldi-themes/): the theme ZIP holds one or two files, the JSON with the parameters and the optional background image; importing is *Settings → Themes → Library → Open Theme*, and it needs Vivaldi 5.0 or newer.
- Real exports in the wild: the `catppuccin/vivaldi` build (`build.ts`, `base_settings.json`) writes `settings.json` at the ZIP root next to `background.jpg`, with the keys `accentFromPage`, `accentOnWindow`, `accentSaturationLimit`, `alpha`, `backgroundImage`, `backgroundPosition`, `blur`, `colorAccentBg`, `colorBg`, `colorFg`, `colorHighlightBg`, `colorWindowBg`, `contrast`, `dimBlurred`, `engineVersion`, `id`, `name`, `preferSystemAccent`, `radius`, `simpleScrollbar`, `transparencyTabBar`, `transparencyTabs`, `url`, `version`.
- The key set shipped here is the one Vivaldi 8.3.4191.44 stored for these two themes on the author's machine (it adds `colorPosition`, `backgroundSource` and `defaultBackground`). Live check (QA report B1 #5, run with the earlier ZIPs): after importing them into a fresh profile, `id`, `name` and every color key were unchanged, and Vivaldi differed in three keys: it added `dimBlurred: false` and `simpleScrollbar: false`, and it stored `defaultBackground` as the `colorBg` value (`#20252B` for Slate, `#FAFBFC` for Daylight) instead of the canvas value the ZIP then shipped. The ZIPs now ship `defaultBackground` = `bg.surface`, matching what Vivaldi stored; `dimBlurred` and `simpleScrollbar` are left to Vivaldi's defaults. No Export dialog was diffed.
- Vivaldi Tip #9, [custom CSS modifications](https://vivaldi.com/blog/tips/tip-9): the experiment is *Allow for using CSS modifications* in that post; in Vivaldi 8.3.4191.44 `vivaldi://experiments` opens `chrome://flags/` and the entry is named *Allow CSS modifications* (`#vivaldi-css-mods`), the folder is chosen in *Settings → Appearance → Custom UI Modifications*, and a restart applies it.
