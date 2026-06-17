#!/usr/bin/env python3
"""Static-site exporter for the EPL website.

`epl serve` registers routes as absolute paths (/, /terms, /privacy, /refund).
Those absolute hrefs only resolve under a live server or a host that does folder
routing -- they break when the HTML is opened as a local file (file:///C:/terms)
and on plain static hosts.

This script renders each route exactly as `epl serve` emits it, then rewrites the
internal absolute links to relative .html links. The result works identically
when double-clicked locally AND when deployed to GitHub Pages / Netlify / Azure
Static / Cloudflare Pages -- no server config required.

It is fully self-contained: it drives the published `epl` package via
`python -m epl serve` (see requirements.txt), so this repo needs no copy of the
EPL compiler.

Usage:
    python build.py                # -> ./dist/
    python build.py --out site     # custom output dir
"""

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, 'src', 'main.epl')

# route path -> output filename
ROUTES = {
    '/': 'index.html',
    '/terms': 'terms.html',
    '/privacy': 'privacy.html',
    '/refund': 'refund.html',
}

# absolute-link -> relative-link rewrites (order matters: longest first)
LINK_MAP = [
    ('href="/terms"', 'href="terms.html"'),
    ('href="/privacy"', 'href="privacy.html"'),
    ('href="/refund"', 'href="refund.html"'),
    ('href="/#install"', 'href="index.html#install"'),
    ('href="/"', 'href="index.html"'),
]
# also handle the same paths when they carry a #fragment, e.g. /terms#scope
FRAG_MAP = {
    '/terms': 'terms.html',
    '/privacy': 'privacy.html',
    '/refund': 'refund.html',
    '/': 'index.html',
}


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def rewrite_links(html: str) -> str:
    for src, dst in LINK_MAP:
        html = html.replace(src, dst)

    # href="/terms#anchor" -> href="terms.html#anchor"
    def _frag(m):
        path, frag = m.group(1), m.group(2)
        target = FRAG_MAP.get(path)
        if target is None:
            return m.group(0)
        return f'href="{target}#{frag}"'

    html = re.sub(r'href="(/[a-z]*)#([^"]+)"', _frag, html)
    return html


def fix_headings(html: str) -> str:
    """Repair the homepage heading hierarchy WITHOUT changing the visible layout.

    The DSL emits `Heading` as a bare <h1> (so the footer column labels became the
    page's only <h1>s) while the real headlines are styled <div>s that contain <p>
    elements. We can't simply turn those divs into <h1>/<h2> -- a <p> is illegal
    inside a heading, so the browser would auto-close the heading and eject the
    text, breaking the layout. Instead:

      * demote the bogus footer <h1>s to <h2> (their content is plain text -> valid),
      * inject one real, visually-hidden <h1> carrying the hero headline (SEO + SR),
      * mark the visible section headlines as ARIA headings (no DOM/layout change).
    """
    # footer column labels (bare <h1>, plain text) -> <h2>
    html = re.sub(r'<h1>(.*?)</h1>', r'<h2>\1</h2>', html, flags=re.S)

    # one real <h1> for search engines and screen readers (visually hidden)
    hero_h1 = ('<h1 class="sr-only">Write code the way you think. '
               'In plain English.</h1>')
    html = re.sub(r'(<header class="hero"[^>]*>)', r'\1' + hero_h1, html, count=1)

    # give the visible section / CTA headlines heading semantics (ARIA only)
    html = re.sub(r'<div class="sec-h([^"]*)">',
                  r'<div role="heading" aria-level="2" class="sec-h\1">', html)
    html = re.sub(r'<div class="cta-h([^"]*)">',
                  r'<div role="heading" aria-level="2" class="cta-h\1">', html)
    return html


# Canonical absolute URL of the deployed site (Azure Static Web App host).
SITE_URL = 'https://wonderful-desert-081e2a400.7.azurestaticapps.net/'


def inject_meta(html: str) -> str:
    """Add og:image / og:url / og:site_name / twitter:image to <head>.

    The DSL parser treats `image`/`url`/`site_name` as reserved keywords and drops
    them from OpenGraph/Twitter directives, so these tags can't be authored in the
    .epl source. We inject them here, after the og:title tag the DSL does emit.
    """
    tags = (
        f'<meta property="og:image" content="{SITE_URL}og.png">'
        f'<meta property="og:url" content="{SITE_URL}">'
        f'<meta property="og:site_name" content="EPL">'
        f'<meta name="twitter:image" content="{SITE_URL}og.png">'
        f'<link rel="canonical" href="{SITE_URL}">'
    )
    anchor = '<meta property="og:title"'
    if anchor in html and 'og:image' not in html:
        html = html.replace(anchor, tags + anchor, 1)
    return html


def main():
    out_dir = os.path.join(HERE, 'dist')
    if '--out' in sys.argv:
        out_dir = os.path.abspath(sys.argv[sys.argv.index('--out') + 1])
    os.makedirs(out_dir, exist_ok=True)

    port = _free_port()
    proc = subprocess.Popen(
        # builtin engine: a one-shot static render needs no production WSGI
        # server, and it sidesteps optional-dependency drift (e.g. waitress).
        [sys.executable, '-m', 'epl', 'serve', SOURCE, '--port', str(port),
         '--engine', 'builtin'],
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # wait for the server to come up
        base = f'http://127.0.0.1:{port}'
        up = False
        for _ in range(40):
            try:
                urllib.request.urlopen(base + '/', timeout=1).read()
                up = True
                break
            except Exception:
                time.sleep(0.5)
        if not up:
            print('Error: server did not start', file=sys.stderr)
            return 1

        written = []
        for route, fname in ROUTES.items():
            html = urllib.request.urlopen(base + route, timeout=10).read().decode('utf-8')
            html = rewrite_links(html)
            if route == '/':
                html = fix_headings(html)
                html = inject_meta(html)
            path = os.path.join(out_dir, fname)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(html)
            written.append((fname, len(html)))

        # social preview image: copy alongside the HTML if present
        og_src = os.path.join(HERE, 'assets', 'og.png')
        if os.path.exists(og_src):
            import shutil
            shutil.copy(og_src, os.path.join(out_dir, 'og.png'))
            written.append(('og.png', os.path.getsize(og_src)))

        print(f'Static site exported to: {out_dir}')
        for fname, size in written:
            print(f'  {fname:14} {size:>7,} bytes')
        print('\nOpen dist/index.html directly, or deploy the dist/ folder to any static host.')
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    raise SystemExit(main())
