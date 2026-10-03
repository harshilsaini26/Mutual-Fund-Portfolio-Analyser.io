# The README's tour

A 20-second tour of the public site, made with [Remotion](https://www.remotion.dev)
from real screenshots of it, and the screenshots the main README shows. Nothing here
is part of the site or the app; CI and the nightly build never touch it.

```bash
cd video
npm ci
npm run shots     # screenshots of the published site -> public/shots/*.png
npm run studio    # preview and edit the scenes
npm run gif       # render -> tour.gif, the README's inline tour
```

`npm run shots` drives an installed Chrome or Edge through its debugging protocol (no
packages): light theme, reduced motion, so every scroll-built picture is captured
finished. The portfolio page is shown with an example SIP and lump sum written to
that page's own browser storage. Pass another address to capture a local build:
`node scripts/capture.mjs http://localhost:8804`.

`npm run gif` renders with Remotion's own browser. To use an installed Chrome
instead, add `--browser-executable="<path to chrome>"`.

The font is the site's own, Terminess Nerd Font (Terminus by Dimitar Zhekov, SIL Open
Font License 1.1), copied from `src/m6_views/static/fonts/`.
