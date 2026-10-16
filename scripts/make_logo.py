"""Generate the CourtOfCode logo: scales of justice fused with code chevrons.

Draws at 4x supersampling for clean anti-aliased edges, then downscales to a
512x512 PNG well under 500 KB. Written to frontend/public/logo.png and docs/logo.png.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = 512
SS = 4  # supersample factor
CANVAS = SIZE * SS

# Palette
BG_TOP = (11, 16, 32)  # deep navy
BG_BOT = (6, 10, 20)
SILVER = (201, 212, 227)
SILVER_DK = (120, 134, 158)
CLAIM = (34, 211, 238)  # cyan - claimant pan
RESP = (245, 158, 11)  # amber - respondent pan
GOLD = (226, 190, 96)  # pivot / finial


def s(v):
    return int(round(v * SS))


def main():
    img = Image.new("RGB", (CANVAS, CANVAS), BG_BOT)
    d = ImageDraw.Draw(img)

    # Vertical background gradient
    for y in range(CANVAS):
        t = y / CANVAS
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        d.line([(0, y), (CANVAS, y)], fill=(r, g, b))

    cx = CANVAS // 2

    # Rounded frame
    d.rounded_rectangle([s(24), s(24), s(488), s(488)], radius=s(60),
                        outline=SILVER_DK, width=s(4))

    # Central column
    d.rectangle([s(248), s(96), s(264), s(392)], fill=SILVER)
    # Base (two tiers)
    d.polygon([(s(188), s(414)), (s(324), s(414)), (s(300), s(392)),
               (s(212), s(392))], fill=SILVER)
    d.rectangle([s(170), s(414), s(342), s(428)], fill=SILVER_DK)

    # Finial on top
    d.ellipse([s(244), s(74), s(268), s(98)], fill=GOLD)

    # Beam
    d.rectangle([s(96), s(128), s(416), s(138)], fill=SILVER)
    d.ellipse([s(240), s(120), s(272), s(152)], fill=GOLD)

    # Hangers from beam ends
    for bx in (110, 402):
        d.line([(s(bx), s(134)), (s(bx - 44), s(214))], fill=SILVER_DK, width=s(4))
        d.line([(s(bx), s(134)), (s(bx + 44), s(214))], fill=SILVER_DK, width=s(4))

    # Left pan: "<" chevron (claimant) - apex on the left
    draw_chevron(d, apex=(s(132), s(258)), arm_top=(s(212), s(196)),
                 arm_bot=(s(212), s(320)), color=CLAIM)
    # Right pan: ">" chevron (respondent) - apex on the right
    draw_chevron(d, apex=(s(380), s(258)), arm_top=(s(300), s(196)),
                 arm_bot=(s(300), s(320)), color=RESP)

    # Glow dots at apexes
    d.ellipse([s(126), s(252), s(140), s(266)], fill=CLAIM)
    d.ellipse([s(372), s(252), s(386), s(266)], fill=RESP)

    out = img.resize((SIZE, SIZE), Image.LANCZOS)

    for rel in ("frontend/public/logo.png", "docs/logo.png"):
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        out.save(p, format="PNG", optimize=True)
        print(f"wrote {p} ({p.stat().st_size} bytes)")


def draw_chevron(d, apex, arm_top, arm_bot, color):
    width = s(26)
    d.line([arm_top, apex, arm_bot], fill=color, width=width, joint="curve")
    outline = tuple(max(0, c - 90) for c in color)
    d.line([arm_top, apex, arm_bot], fill=(*color, ), width=s(10))


if __name__ == "__main__":
    main()
