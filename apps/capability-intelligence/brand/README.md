# Zennify brand assets

Drop the canonical logo here:

  static/brand/logo.png   # square / icon teal (#27BBAF) on transparent
  static/brand/logo.svg   # vector preferred

The PPTX renderer (`services/pptx_export.py::_add_title_slide`)
auto-includes the logo when it finds `logo.png` or `logo.svg` in this
folder. Without an asset, the title slide falls back to the wordmark.

Brand palette (locked per spec §14, mirrored in
`frontend/tailwind.config.ts` and `services/pptx_export.py`):

| Token             | Hex     | Use                          |
|-------------------|---------|------------------------------|
| zen-dark-green    | #1C4A4D | Headlines, sidebar bg        |
| zen-dark-teal     | #185F60 | Body text, muted UI          |
| zen-teal          | #27BBAF | **Icon teal** — brand accent |
| zen-light-teal    | #62D7B8 | Wordmark, hover states       |
| zen-light-green   | #B0EED3 | Cards, soft fills            |
| zen-white-green   | #E8F7F6 | Page background              |
| zen-light-orange  | #FFCB99 | Tier T4, warnings            |
| zen-orange        | #FE9732 | Tier T5, criticals           |
