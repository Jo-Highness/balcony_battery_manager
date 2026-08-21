# Screenshots

The main [`README.md`](../README.md) references three screenshots from this
folder. The maintainer must produce and commit these images — they are not
generated automatically. Use a clean Home Assistant instance and keep the theme
consistent across all three.

Recommended: **PNG**, **light theme** (the default Home Assistant theme), captured
at a normal desktop browser width. Crop tightly to the relevant UI.

| File | Motif | Recommended size |
|---|---|---|
| `config-flow.png` | The single-step **Add Integration** configuration form, showing the input/actor entity pickers and the tunable parameters with their prefilled defaults. | ~1280 × 900 px |
| `entities.png` | The **Balcony Battery Manager** device page listing its entities: the *Mode* sensor (with its attributes), *Target power*, *Corrected demand*, *Surplus*, and the *Enabled* switch. | ~1280 × 900 px |
| `dashboard.png` | A Lovelace dashboard card (or set of cards) showing the controller in operation — e.g. current mode, target power and corrected demand over time. | ~1280 × 720 px |

Notes:

- Keep filenames exactly as above so the README image links resolve.
- Prefer the light theme for legibility on GitHub and in the HACS store; if you
  add dark-theme variants, keep the light versions at these filenames.
- Avoid exposing personal data (real entity names, locations) where practical.
