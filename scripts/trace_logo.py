"""Trace the user's codeblue logo PNG into clean vector SVGs.

Each brand colour is separated into its own high-resolution mask, traced with
vtracer (binary, spline curves), then recombined with the exact brand colours.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "tracetools2"), os.path.join(HERE, "pydeps")]
from PIL import Image, ImageFilter  # noqa: E402
import numpy  # noqa: E402
import potrace  # noqa: E402

SRC = os.path.join(os.path.dirname(HERE), "images", "1.png")
OUT = r"C:\Users\stephan.vanvuuren\.gemini\antigravity\scratch\stephan-network-tester\frontend\static\brand"
NAVY = (15, 66, 95)
LIGHT = (133, 198, 255)
SCALE = 8

im = Image.open(SRC).convert("RGB")
crop = (19 - 6, 13 - 6, 488 + 6, 129 + 6)  # tight box around the artwork + margin
im = im.crop(crop)
W, H = im.size
big = im.resize((W * SCALE, H * SCALE), Image.LANCZOS)


def coverage(px, target):
    """0..1: how much of this (anti-aliased) pixel is `target` colour over white."""
    # project the pixel onto the white->target line
    num = sum((255 - p) * (255 - t) for p, t in zip(px, target))
    den = sum((255 - t) ** 2 for t in target)
    return max(0.0, min(1.0, num / den))


def color_dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def mask_for(target, other):
    m = Image.new("L", big.size, 255)
    src = big.load()
    dst = m.load()
    for y in range(big.size[1]):
        for x in range(big.size[0]):
            px = src[x, y]
            if px[0] > 245 and px[1] > 245 and px[2] > 245:
                continue
            # pixel belongs to whichever brand colour it is closer to
            if color_dist(px, target) < color_dist(px, other):
                if coverage(px, target) >= 0.5:
                    dst[x, y] = 0
    return m.filter(ImageFilter.MedianFilter(5))


def trace(mask_img, name):
    """Trace a black-on-white mask with potrace; return one SVG path 'd' string (even-odd fill)."""
    mask_img.save(os.path.join(HERE, f"mask_{name}.png"))
    arr = numpy.array(mask_img) >= 128  # potracer fills the False regions, so ink must be False
    bm = potrace.Bitmap(arr)
    plist = bm.trace(turdsize=60, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY, alphamax=1.0,
                     opticurve=True, opttolerance=0.2)
    f = lambda p: f"{p.x:.0f} {p.y:.0f}"
    parts = []
    for curve in plist:
        d = [f"M{f(curve.start_point)}"]
        for seg in curve.segments:
            if seg.is_corner:
                d.append(f"L{f(seg.c)}L{f(seg.end_point)}")
            else:
                d.append(f"C{f(seg.c1)} {f(seg.c2)} {f(seg.end_point)}")
        d.append("Z")
        parts.append("".join(d))
    return [f'<path fill-rule="evenodd" d="{"".join(parts)}"/>']

def recolor(paths, fill):
    out = []
    for p in paths:
        p = re.sub(r'fill="[^"]*"', "", p)
        out.append(p.replace("<path", f'<path fill="{fill}"', 1))
    return out


navy_paths = trace(mask_for(NAVY, LIGHT), "navy")
light_paths = trace(mask_for(LIGHT, NAVY), "light")
print("paths:", len(navy_paths), len(light_paths))

VW, VH = W * SCALE, H * SCALE


def write(name, navy_fill, light_fill, title):
    body = "\n".join(recolor(navy_paths, navy_fill) + recolor(light_paths, light_fill))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VW} {VH}" role="img" aria-label="codeblue IT services">\n'
           f"<title>{title}</title>\n{body}\n</svg>\n")
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print(name, len(svg), "bytes")


write("codeblue-logo.svg", "#0F425F", "#85C6FF", "codeblue IT services")
write("codeblue-logo-white.svg", "#FFFFFF", "#85C6FF", "codeblue IT services (for dark backgrounds)")
print("viewBox", VW, VH)


# ---- PNG renders for PDFs (transparent background) and the favicon mark ----
ASSETS = r"C:\Users\stephan.vanvuuren\.gemini\antigravity\scratch\stephan-network-tester\backend\assets"
os.makedirs(ASSETS, exist_ok=True)
m_navy = Image.open(os.path.join(HERE, "mask_navy.png")).convert("L")
m_light = Image.open(os.path.join(HERE, "mask_light.png")).convert("L")
half = (m_navy.size[0] // 2, m_navy.size[1] // 2)  # 4x the original artwork: crisp in print


def render(navy_rgb, light_rgb, name):
    canvas = Image.new("RGBA", half, (0, 0, 0, 0))
    for mask, rgb in ((m_navy, navy_rgb), (m_light, light_rgb)):
        alpha = Image.eval(mask, lambda v: 255 - v).resize(half, Image.LANCZOS)
        layer = Image.new("RGBA", half, rgb + (255,))
        layer.putalpha(alpha)
        canvas = Image.alpha_composite(canvas, layer)
    canvas.save(os.path.join(ASSETS, name), optimize=True)
    print(name, canvas.size)


render(NAVY, LIGHT, "codeblue-logo.png")
render((255, 255, 255), LIGHT, "codeblue-logo-white.png")

# Favicon: the traced power symbol, white-on-navy rounded square
ink = Image.eval(m_light, lambda v: 255 - v)
bx = ink.getbbox()
light_d = re.search(r'd="([^"]+)"', light_paths[0]).group(1)
side = max(bx[2] - bx[0], bx[3] - bx[1])
pad = side * 0.22
vb = (bx[0] + (bx[2] - bx[0]) / 2 - side / 2 - pad, bx[1] + (bx[3] - bx[1]) / 2 - side / 2 - pad, side + 2 * pad)
mark = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]:.0f} {vb[1]:.0f} {vb[2]:.0f} {vb[2]:.0f}" role="img" aria-label="codeblue">\n'
        f'<title>codeblue</title>\n'
        f'<rect x="{vb[0]:.0f}" y="{vb[1]:.0f}" width="{vb[2]:.0f}" height="{vb[2]:.0f}" rx="{vb[2] * 0.22:.0f}" fill="#0F425F"/>\n'
        f'<path fill="#85C6FF" fill-rule="evenodd" d="{light_d}"/>\n</svg>\n')
with open(os.path.join(OUT, "codeblue-mark.svg"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write(mark)
print("mark", len(mark), "bytes")