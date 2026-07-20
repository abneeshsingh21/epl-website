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
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, 'src', 'main.epl')

# route path -> output filename
ROUTES = {
    '/': 'index.html',
    '/what-is-epl': 'what-is-epl.html',
    '/terms': 'terms.html',
    '/privacy': 'privacy.html',
    '/refund': 'refund.html',
}
ICON_ASSETS = [
    'favicon.ico',
    'favicon-16x16.png',
    'favicon-32x32.png',
    'favicon-48x48.png',
    'favicon-96x96.png',
    'apple-touch-icon.png',
    'android-chrome-192x192.png',
    'android-chrome-512x512.png',
]

# absolute-link -> relative-link rewrites (order matters: longest first)
LINK_MAP = [
    ('href="/what-is-epl"', 'href="what-is-epl.html"'),
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


# Canonical absolute URL of the deployed site (custom domain).
SITE_URL = 'https://eplang.me/'


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


def _faq_jsonld() -> dict:
    """FAQPage schema for /what-is-epl. Q&A text mirrors the visible page
    (Google requires the on-page content to match the markup)."""
    def qa(q, a):
        return {'@type': 'Question', 'name': q,
                'acceptedAnswer': {'@type': 'Answer', 'text': a}}
    return {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            qa('Is EPL a real programming language?',
               'Yes. EPL is a genuine general-purpose language with a lexer, '
               'parser, type checker, bytecode virtual machine, LLVM native '
               'compiler, test framework, and package manager. Programs run, '
               'compile, and ship to production.'),
            qa('Is EPL free to use?',
               'Yes. EPL is open source under the Apache-2.0 license. The '
               'compiler, standard library, VS Code extension, and browser '
               'playground are all free, for commercial and personal use alike.'),
            qa('How do I install EPL?',
               'Install Python 3.9 or newer, then run pip install eplang. '
               'Verify the installation with epl --version and run your first '
               'program with epl run hello.epl. You can also try the language '
               'in the browser playground without installing anything.'),
            qa('What does EPL stand for?',
               'EPL stands for English Programming Language. The acronym is '
               'also used in unrelated fields; in software development, EPL '
               'refers to this language, with its official website at eplang.me.'),
            qa('Can EPL build production applications?',
               'Yes. EPL builds web servers and JSON APIs with routing, SQLite, '
               'and authentication built in; command-line tools; desktop '
               'applications; and standalone native binaries. The eplang.me '
               'website itself is written in EPL.'),
        ],
    }


def inject_jsonld(html: str, route: str = '/') -> str:
    """Add JSON-LD structured data (schema.org) to a page <head>.

    Only verifiable facts: name, publisher, license, install target, repo.
    No ratings/reviews — search engines penalize unverifiable claims.
    The /what-is-epl page also gets a FAQPage block matching its visible Q&A.
    """
    import json
    page_url = SITE_URL if route == '/' else SITE_URL + route.lstrip('/')
    data = [
        {
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            'name': 'EPL — English Programming Language',
            'alternateName': ['EPL', 'eplang', 'English Programming Language'],
            'url': SITE_URL,
        } if route == '/' else {
            '@context': 'https://schema.org',
            '@type': 'WebPage',
            'name': 'What is EPL? — The English Programming Language',
            'url': page_url,
            'isPartOf': {'@type': 'WebSite', 'name': 'EPL', 'url': SITE_URL},
        },
        {
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            'name': 'EPL (English Programming Language)',
            'alternateName': 'eplang',
            'description': (
                'A programming language with plain-English syntax. '
                'Runs on a bytecode VM, compiles to native binaries via LLVM, '
                'and transpiles to Python, JavaScript, Kotlin and more.'
            ),
            'url': SITE_URL,
            'applicationCategory': 'DeveloperApplication',
            'operatingSystem': 'Windows, macOS, Linux',
            'license': 'https://www.apache.org/licenses/LICENSE-2.0',
            'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'},
            'downloadUrl': 'https://pypi.org/project/eplang/',
            'installUrl': 'https://pypi.org/project/eplang/',
            'codeRepository': 'https://github.com/abneeshsingh21/EPL',
            'author': {'@type': 'Person', 'name': 'Abneesh Singh'},
            'programmingLanguage': {'@type': 'ComputerLanguage', 'name': 'EPL'},
        },
    ]
    if route == '/what-is-epl':
        data.append(_faq_jsonld())
    blocks = ''.join(
        '<script type="application/ld+json">'
        + json.dumps(d, separators=(',', ':'))
        + '</script>'
        for d in data
    )
    if 'application/ld+json' not in html:
        html = html.replace('</head>', blocks + '</head>', 1)
    return html


def inject_icon_links(html: str) -> str:
    """Add the standard favicon variants beside EPL's base Favicon output."""
    tags = (
        '<link rel="icon" type="image/png" sizes="16x16" href="favicon-16x16.png">'
        '<link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png">'
        # Google Search requires a favicon at a multiple of 48x48 to show a
        # site icon in results; without one it renders the generic globe.
        '<link rel="icon" type="image/png" sizes="48x48" href="favicon-48x48.png">'
        '<link rel="icon" type="image/png" sizes="96x96" href="favicon-96x96.png">'
        '<link rel="icon" type="image/png" sizes="192x192" href="android-chrome-192x192.png">'
        '<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">'
        '<link rel="manifest" href="site.webmanifest">'
    )
    if 'apple-touch-icon' not in html:
        html = html.replace('<link rel="icon" type="image/x-icon" href="favicon.ico">',
                            '<link rel="icon" type="image/x-icon" href="favicon.ico">' + tags,
                            1)
    return html


def copy_static_assets(out_dir: str):
    written = []
    assets_dir = os.path.join(HERE, 'assets')

    for fname in ICON_ASSETS:
        src = os.path.join(assets_dir, fname)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, fname))
            written.append((fname, os.path.getsize(src)))

    manifest = (
        '{"name":"EPL","short_name":"EPL","icons":['
        '{"src":"android-chrome-192x192.png","sizes":"192x192","type":"image/png"},'
        '{"src":"android-chrome-512x512.png","sizes":"512x512","type":"image/png"}'
        '],"theme_color":"#ffffff","background_color":"#ffffff","display":"standalone"}'
    )
    manifest_path = os.path.join(out_dir, 'site.webmanifest')
    with open(manifest_path, 'w', encoding='utf-8') as fh:
        fh.write(manifest)
    written.append(('site.webmanifest', len(manifest)))

    og_src = os.path.join(assets_dir, 'og.png')
    if os.path.exists(og_src):
        shutil.copy(og_src, os.path.join(out_dir, 'og.png'))
        written.append(('og.png', os.path.getsize(og_src)))

    # crawler/discovery files: robots.txt + sitemap.xml (search engines),
    # llms.txt (AI assistants — mirrors the one in the main EPL repo)
    for fname in ('robots.txt', 'sitemap.xml', 'llms.txt', 'llms-full.txt'):
        src = os.path.join(assets_dir, fname)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, fname))
            written.append((fname, os.path.getsize(src)))

    return written


def main():
    out_dir = os.path.join(HERE, 'dist')
    if '--out' in sys.argv:
        idx = sys.argv.index('--out')
        if idx + 1 >= len(sys.argv):
            print('Error: --out requires a directory argument', file=sys.stderr)
            return 2
        out_dir = os.path.abspath(sys.argv[idx + 1])
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
            html = inject_icon_links(html)
            if route == '/':
                html = fix_headings(html)
                html = inject_meta(html)
                html = inject_jsonld(html)
            elif route == '/what-is-epl':
                page_url = SITE_URL + route.lstrip('/')
                if 'rel="canonical"' not in html:
                    html = html.replace(
                        '</head>',
                        f'<link rel="canonical" href="{page_url}">'
                        f'<meta name="robots" content="index,follow">'
                        f'<meta property="og:url" content="{page_url}">'
                        f'<meta property="og:type" content="article">'
                        '</head>', 1)
                html = inject_jsonld(html, route)
            path = os.path.join(out_dir, fname)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(html)
            written.append((fname, len(html)))

        written.extend(copy_static_assets(out_dir))

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
