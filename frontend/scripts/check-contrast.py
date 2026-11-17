"""WCAG contrast of the design-token text/background pairs, both themes.
Run: python3 scripts/check-contrast.py   (exits 1 if any pair is below AA 4.5:1)"""
import re
import sys
from pathlib import Path

CSS = (Path(__file__).parents[1] / "src" / "tokens.css").read_text()
PAIRS = [("text", "bg"), ("text", "surface"), ("text-secondary", "surface"), ("text-muted", "surface"),
         ("text-muted", "bg"), ("text-muted", "surface-subtle"), ("accent-text", "surface"),
         ("accent-text", "accent-soft"), ("text-on-accent", "accent"), ("text", "user-bubble"),
         ("success-text", "success-soft"), ("warning-text", "warning-soft"), ("danger-text", "danger-soft"),
         ("code-text", "code-bg")]


def tokens(selector):
    start = CSS.index(selector)
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", CSS[start:CSS.index("}", start)]))


def rgb(value, under=(255, 255, 255)):
    value = value.strip()
    if value.startswith("#"):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b, a = (float(x) for x in re.findall(r"[\d.]+", value))
    return tuple(round(c * a + u * (1 - a)) for c, u in zip((r, g, b), under))  # composite over `under`


def luminance(c):
    lin = [x / 255 / 12.92 if x / 255 <= 0.03928 else ((x / 255 + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


failures = 0
for theme in ("light", "dark"):
    t = tokens(f':root[data-theme="{theme}"]')
    surface = rgb(t["surface"])
    for fg, bg in PAIRS:
        background = rgb(t[bg], surface)
        r = ratio(rgb(t[fg], background), background)
        failures += r < 4.5
        print(f"{theme:5} {fg:15} on {bg:15} {r:5.2f} {'OK' if r >= 4.5 else 'LOW'}")
sys.exit(1 if failures else 0)
