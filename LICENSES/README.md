# License notes

This repository has mixed licenses.

| Files | License |
| :--- | :--- |
| Everything not listed below (`css/`, `scripts/`, `src/`, `docs/`, `examples/`, the theme ZIPs, the images) | MIT, see [`../LICENSE`](../LICENSE) |
| `css/flatcap-extensions-list.css` | **GPL-3.0**, see [`GPL-3.0.txt`](GPL-3.0.txt) |

Why: `css/flatcap-extensions-list.css` follows the structure of `Extensions.css` from [Awesome-Vivaldi](https://github.com/PaRr0tBoY/Awesome-Vivaldi) (GPL-3.0; authors @quodroc and PaRr0tBoY): the same selectors and several identical declarations. The file's header says so. Flatcap adds the tokens, sizing, focus ring and states.

What it means for you:

- Copying only MIT files keeps you under MIT. Do not copy `flatcap-extensions-list.css` if you want a purely MIT set.
- If you distribute a package that includes `flatcap-extensions-list.css`, that file stays GPL-3.0 and comes with its source and the GPL-3.0 text. Whether the GPL-3.0 terms reach the other files of such a package is a legal question this repository does not answer.
- The other layers (`flatcap-audio-quiet.css`, `flatcap-downloads.css`) are inspired by ideas of the same project but contain no code taken from it, see the README, *Third-party code and licenses*.

**Status:** the final decision on `flatcap-extensions-list.css` belongs to the repository owner (keep it GPL-3.0 with attribution, or remove the file and its row). Until it is taken, the file stays GPL-3.0. This note is not legal advice.
