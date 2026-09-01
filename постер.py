#!/usr/bin/env python3
"""Картинка под пост: реальный лог деска, отрисованный как терминал.

    python3 постер.py                  → docs/media/post.png (1600x900)
    python3 постер.py --lines 12       сколько строк лога взять
    python3 постер.py --out путь.png

Берёт docs/data/log.json и latest.json - то есть на картинке ровно то, что
сейчас на сайте. Ничего не выдумывает: если строки нет в логе, её нет и здесь.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "docs", "data", "log.json")
LATEST = os.path.join(ROOT, "docs", "data", "latest.json")
CREST = os.path.join(ROOT, "docs", "media", "coin.png")
WORD = os.path.join(ROOT, "docs", "media", "wordmark.png")

INK = (0, 0, 0)
DIM = (72, 96, 110)
TEXT = (185, 199, 210)
CREAM = (232, 228, 217)
TEAL = (45, 212, 191)
DENY = (255, 92, 82)
AMBER = (242, 176, 74)
GRID = (26, 38, 46)

COLOURS = {"scan": DIM, "read": TEAL, "deny": DENY, "pass": TEAL, "done": AMBER}


def font(size: int, bold: bool = False):
    for path, index in (
        ("/System/Library/Fonts/Menlo.ttc", 1 if bold else 0),
        ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 0),
    ):
        try:
            return ImageFont.truetype(path, size, index=index)
        except Exception:
            continue
    return ImageFont.load_default()


def load(path: str, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def wrap(draw, text: str, face, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        probe = (line + " " + word).strip()
        if draw.textlength(probe, font=face) <= width:
            line = probe
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def interesting(log: list[dict], rows: int) -> list[dict]:
    """Хвост лога, но без стены одинаковых отказов.

    Подряд идущие «wave too thin» читаются как одна строка, повторённая
    десять раз. Берём не больше двух одинаковых причин подряд, чтобы на
    картинке был виден весь круг: сканирование, чтение чейна, вердикт.
    """
    picked: list[dict] = []
    seen_reason: dict[str, int] = {}
    for row in reversed(log):
        text = row.get("text", "")
        # "DENY $PETEY - R2 MIDWIFE wave too thin: ..." → "R2 MIDWIFE wave too thin"
        reason = (
            text.split(" - ", 1)[-1].split(":")[0]
            if row.get("kind") == "deny"
            else row.get("kind", "")
        )
        if seen_reason.get(reason, 0) >= 2:
            continue
        seen_reason[reason] = seen_reason.get(reason, 0) + 1
        picked.append(row)
        if len(picked) >= rows:
            break
    return list(reversed(picked))


def build(rows: int, out: str) -> str:
    log = interesting(load(LOG, []), rows)
    latest = load(LATEST, {})
    W, H = 1600, 900
    image = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(image)

    for x in range(24, W, 44):
        for y in range(24, H, 44):
            draw.rectangle([x, y, x + 1, y + 1], fill=GRID)

    # шапка: герб и слово
    try:
        crest = Image.open(CREST).convert("RGBA").resize((104, 104), Image.NEAREST)
        image.paste(crest, (64, 56), crest)
    except Exception:
        pass
    try:
        word = Image.open(WORD).convert("RGBA")
        word = word.resize((470, max(1, int(word.height * 470 / word.width))), Image.NEAREST)
        image.paste(word, (196, 84), word)
    except Exception:
        pass

    ledger = latest.get("ledger") or {}
    seen = latest.get("seen") or {}
    draw.text(
        (196, 132),
        f"live desk log  ·  {ledger.get('refusals_recorded', 0):,} refusals on the book"
        f"  ·  {seen.get('launches_pulled', 0):,} mints scanned this run",
        font=font(19),
        fill=DIM,
    )

    # рамка терминала
    top, left, right = 210, 64, W - 64
    draw.rectangle([left, top, right, H - 96], outline=(22, 33, 42), width=2)
    draw.rectangle([left, top, right, top + 44], fill=(11, 17, 22))
    for i, colour in enumerate((DENY, (29, 42, 51), (29, 42, 51))):
        draw.ellipse([left + 22 + i * 22, top + 17, left + 32 + i * 22, top + 27], fill=colour)
    draw.text((left + 100, top + 14), "warden@desk - live", font=font(16), fill=DIM)

    face, small = font(20), font(20)
    y = top + 72
    for row in log:
        colour = COLOURS.get(row.get("kind", ""), TEXT)
        stamp = time.strftime("%H:%M:%S", time.gmtime(row.get("at", 0)))
        draw.text((left + 26, y), stamp, font=small, fill=(44, 63, 75))
        for line in wrap(draw, row.get("text", ""), face, right - left - 190)[:2]:
            draw.text((left + 150, y), line, font=face, fill=colour)
            y += 27
        y += 7
        if y > H - 150:
            break

    coin = latest.get("coin") or {}
    footer = "a refusal has no chart  ·  jugqdc-sudo.github.io/warden-desk"
    if coin.get("cap_usd"):
        footer = (
            f"${coin.get('ticker', 'WARDEN')}  ·  cap ${round(coin['cap_usd']):,}"
            f"  ·  {coin.get('holders', '?')}"
            f"{'' if coin.get('holders_exact', True) else '+'} holders"
            f"     jugqdc-sudo.github.io/warden-desk"
        )
    draw.text((left, H - 72), footer, font=font(21), fill=CREAM)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    image.save(out, quality=95)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="картинка под пост из живого лога")
    parser.add_argument("--lines", type=int, default=11)
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "media", "post.png"))
    args = parser.parse_args()
    path = build(args.lines, args.out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
