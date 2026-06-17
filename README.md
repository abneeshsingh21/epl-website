# EPL — Website

The official marketing site for **[EPL](https://github.com/abneeshsingh21/EPL)**, the
English-like programming language. What makes this repo unusual: **the website is
itself written in EPL.** There is no HTML, CSS framework, or JS build chain in the
source — `src/main.epl` is a single EPL program that emits the entire page (layout,
design system, animations, and an embedded live playground) through EPL's native web DSL.

A small Python driver (`build.py`) renders that program to static HTML so it can be
hosted anywhere.

---

## Highlights

- **Written in EPL** — the full landing page, legal pages, and an interactive
  playground are authored in `src/main.epl`.
- **Embedded live playground** — a native in-page editor + Run button that executes
  real EPL against the live [playground backend](https://epl-playground.azurewebsites.net).
- **Zero-config static output** — absolute server routes are rewritten to relative
  `.html` links, so the built site works when opened locally *and* on any static host
  (GitHub Pages, Netlify, Cloudflare Pages, Azure Static Web Apps).
- **Continuous deploy** — every push to `main` rebuilds the site and publishes it to
  GitHub Pages via GitHub Actions.

## Project layout

```
.
├── src/
│   └── main.epl          # the entire website, written in EPL
├── build.py              # renders main.epl -> dist/*.html (self-contained)
├── epl.toml              # EPL package manifest
├── requirements.txt      # pins the EPL compiler (epl>=9.7.0)
└── .github/workflows/
    └── deploy.yml         # build + deploy to GitHub Pages
```

## Build locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python build.py
```

This writes `index.html`, `terms.html`, `privacy.html`, and `refund.html` to `dist/`.
Open `dist/index.html` directly in a browser, or serve the folder:

```bash
python -m http.server --directory dist 8123
# then open http://127.0.0.1:8123/
```

To preview with hot-reload straight from source (no static export):

```bash
python -m epl serve src/main.epl --dev
```

## Deployment

Pushes to `main` trigger `.github/workflows/deploy.yml`, which installs the EPL
compiler, runs `python build.py`, and deploys `dist/` to GitHub Pages. To enable it,
set **Settings → Pages → Source = GitHub Actions** once.

The site can also be deployed to any static host by uploading the contents of `dist/`.

## License

[Apache License 2.0](LICENSE) — same as the EPL project.
