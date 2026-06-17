#!/usr/bin/env python3
"""Generate the social-share card (og.png, 1200x630) for the EPL website.

Renders an on-brand light-theme card with the hero headline, a blue accent on
"In plain English.", a one-line feature summary, and a footer wordmark. Run:

    python landing_page/assets/make_og.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'og.png')

W, H = 1200, 630
INK = (255, 255, 255)
PAPER = (17, 17, 19)
DIM = (95, 96, 102)
FAINT = (138, 139, 146)
BLUE = (0, 125, 243)
LINE = (228, 228, 231)


def _font(names, size):
    roots = [r'C:\Windows\Fonts', '/usr/share/fonts', '/Library/Fonts']
    for name in names:
        for root in roots:
            p = os.path.join(root, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    img = Image.new('RGB', (W, H), INK)
    d = ImageDraw.Draw(img)

    # top accent bar (brand blue gradient)
    grad = ('#007DF3', '#2EA0FF', '#5BB8FF')
    stops = [(0, 125, 243), (46, 160, 255), (91, 184, 255)]
    for x in range(W):
        f = x / (W - 1)
        if f < 0.5:
            a, b, t = stops[0], stops[1], f / 0.5
        else:
            a, b, t = stops[1], stops[2], (f - 0.5) / 0.5
        col = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        d.line([(x, 0), (x, 6)], fill=col)

    f_eyebrow = _font(['consola.ttf', 'Consolas.ttf', 'DejaVuSansMono.ttf'], 24)
    f_head = _font(['segoeuib.ttf', 'Arialbd.ttf', 'DejaVuSans-Bold.ttf'], 92)
    f_sub = _font(['segoeui.ttf', 'Arial.ttf', 'DejaVuSans.ttf'], 34)
    f_foot = _font(['consola.ttf', 'Consolas.ttf', 'DejaVuSansMono.ttf'], 26)

    M = 88
    # eyebrow
    d.text((M, 92), 'ENGLISH PROGRAMMING LANGUAGE', font=f_eyebrow, fill=FAINT)
    # blue ping dot
    d.ellipse([M - 30, 100, M - 16, 114], fill=BLUE)

    # headline (two lines; blue accent on the second)
    d.text((M, 150), 'Write code the', font=f_head, fill=PAPER)
    d.text((M, 250), 'way you think.', font=f_head, fill=PAPER)
    d.text((M, 350), 'In plain English.', font=f_head, fill=BLUE)

    # feature summary
    d.text((M, 478),
           'A real language · bytecode VM · LLVM-native · 8 targets · 725+ built-ins',
           font=f_sub, fill=DIM)

    # footer divider + wordmark
    d.line([(M, 556), (W - M, 556)], fill=LINE, width=1)
    d.text((M, 572), 'pip install eplang', font=f_foot, fill=PAPER)
    rt = 'Apache-2.0'
    w = d.textlength(rt, font=f_foot)
    d.text((W - M - w, 572), rt, font=f_foot, fill=FAINT)

    img.save(OUT, 'PNG')
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')


if __name__ == '__main__':
    main()
