"""Generate creative-design and photo-simulated test labels.

Run:  python scripts/generate_creative_labels.py
Adds six labels to ../test_labels/ and extends applications.csv:
  midnight_gin.png        dark modern gin label            -> should pass
  sunset_ipa.png          colorful craft-beer label        -> should pass
  casa_azul_tequila.png   decorative tequila label, 700 mL -> volume mismatch
  velvet_hare_wine.png    wine label with NO warning       -> missing warning
  old_tom_photo.png       simulated photo (angle, shadow)  -> pass / quality note
  old_tom_photo_glare.png simulated bad photo (glare+blur) -> quality issues
"""

import random
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "test_labels"
OUT.mkdir(exist_ok=True)
random.seed(7)

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts"]
FONTS = {
    ("sans", False): ["DejaVuSans.ttf", "arial.ttf"],
    ("sans", True): ["DejaVuSans-Bold.ttf", "arialbd.ttf"],
    ("serif", False): ["DejaVuSerif.ttf", "times.ttf"],
    ("serif", True): ["DejaVuSerif-Bold.ttf", "timesbd.ttf"],
    ("italic", False): ["DejaVuSerif-Italic.ttf", "timesi.ttf"],
}


def font(family="sans", bold=False, size=32):
    for d in FONT_DIRS:
        for n in FONTS[(family, bold)]:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


WARNING = ("GOVERNMENT WARNING:", " (1) According to the Surgeon General, "
           "women should not drink alcoholic beverages during pregnancy "
           "because of the risk of birth defects. (2) Consumption of "
           "alcoholic beverages impairs your ability to drive a car or "
           "operate machinery, and may cause health problems.")


def center(d, img, y, text, f, fill):
    w = d.textlength(text, font=f)
    d.text(((img.width - w) / 2, y), text, font=f, fill=fill)
    bbox = f.getbbox(text)
    return y + (bbox[3] - bbox[1]) + 10


def draw_warning(d, y, width, fill, size=20, wrap_at=64, x_margin=60):
    f_b, f_r = font("sans", True, size), font("sans", False, size)
    full = WARNING[0] + WARNING[1]
    consumed = 0
    for line in wrap(full, width=wrap_at):
        x = x_margin
        if consumed < len(WARNING[0]):
            take = min(len(line), len(WARNING[0]) - consumed)
            head, tail = line[:take], line[take:]
            d.text((x, y), head, font=f_b, fill=fill)
            x += d.textlength(head, font=f_b)
            consumed += take
            d.text((x, y), tail, font=f_r, fill=fill)
        else:
            d.text((x, y), line, font=f_r, fill=fill)
        y += size + 8
    return y


def midnight_gin():
    W, H = 900, 1150
    navy, gold, ice = (18, 24, 48), (212, 175, 55), (235, 240, 250)
    img = Image.new("RGB", (W, H), navy)
    d = ImageDraw.Draw(img)
    d.rectangle([28, 28, W - 28, H - 28], outline=gold, width=3)
    d.rectangle([40, 40, W - 40, H - 40], outline=gold, width=1)
    d.ellipse([W // 2 - 60, 90, W // 2 + 60, 210], fill=gold)
    d.ellipse([W // 2 - 20, 80, W // 2 + 110, 200], fill=navy)
    y = 250
    y = center(d, img, y, "MIDNIGHT", font("sans", True, 96), ice) + 4
    y = center(d, img, y, "LONDON DRY GIN", font("sans", False, 44), gold) + 24
    d.line([(W // 2 - 140, y), (W // 2 + 140, y)], fill=gold, width=2)
    y += 36
    y = center(d, img, y, "Distilled in small batches under a dark sky",
               font("italic", False, 26), ice) + 40
    y = center(d, img, y, "47% Alc./Vol. (94 Proof)", font("sans", False, 36), ice) + 4
    y = center(d, img, y, "750 mL", font("sans", True, 36), ice) + 44
    y = center(d, img, y, "DISTILLED BY NOCTURNE SPIRITS, DENVER, CO",
               font("sans", False, 22), gold) + 8
    y = center(d, img, y, "PRODUCT OF USA", font("sans", False, 22), gold) + 40
    d.line([(60, y), (W - 60, y)], fill=gold, width=1)
    draw_warning(d, y + 20, W, ice, size=21, wrap_at=62)
    img.save(OUT / "midnight_gin.png")


def sunset_ipa():
    W, H = 1000, 950
    img = Image.new("RGB", (W, H), (244, 130, 42))
    d = ImageDraw.Draw(img)
    for i, c in enumerate([(252, 202, 70), (247, 165, 55), (234, 98, 62),
                           (196, 60, 74)]):
        d.rectangle([0, i * 90, W, i * 90 + 90], fill=c)
    d.rectangle([0, 360, W, H], fill=(196, 60, 74))
    d.ellipse([W // 2 - 90, 130, W // 2 + 90, 310], fill=(255, 240, 190))
    d.rounded_rectangle([70, 340, W - 70, H - 40], radius=24,
                        fill=(250, 244, 226), outline=(90, 45, 35), width=4)
    ink = (90, 45, 35)
    y = 365
    y = center(d, img, y, "SUNSET CANYON", font("sans", True, 72), ink)
    y = center(d, img, y, "INDIA PALE ALE", font("sans", False, 42), (196, 60, 74)) + 14
    y = center(d, img, y, "Citrus-forward - Bold - Unfiltered",
               font("italic", False, 26), ink) + 26
    y = center(d, img, y, "6.5% ALC/VOL  -  12 FL OZ", font("sans", True, 34), ink) + 20
    y = center(d, img, y, "BREWED & CANNED BY SUNSET CANYON BREWING, BEND, OR",
               font("sans", False, 20), ink) + 24
    d.line([(110, y), (W - 110, y)], fill=ink, width=2)
    draw_warning(d, y + 18, W, ink, size=20, wrap_at=70, x_margin=110)
    img.save(OUT / "sunset_ipa.png")


def casa_azul():
    W, H = 900, 1100
    cream, azul, terra = (247, 240, 222), (28, 84, 158), (176, 82, 54)
    img = Image.new("RGB", (W, H), cream)
    d = ImageDraw.Draw(img)
    for x in range(40, W - 20, 44):
        d.polygon([(x, 30), (x + 16, 46), (x, 62), (x - 16, 46)], fill=azul)
    d.rectangle([30, 80, W - 30, H - 80], outline=azul, width=4)
    y = 130
    y = center(d, img, y, "- HECHO EN MEXICO -", font("sans", False, 24), terra) + 20
    y = center(d, img, y, "CASA AZUL", font("serif", True, 88), azul) + 6
    y = center(d, img, y, "TEQUILA REPOSADO", font("sans", False, 44), terra) + 20
    d.line([(W // 2 - 160, y), (W // 2 + 160, y)], fill=azul, width=3)
    y += 30
    y = center(d, img, y, "Rested 8 months in oak barrels",
               font("italic", False, 26), (60, 60, 60)) + 36
    y = center(d, img, y, "40% Alc./Vol. (80 Proof)", font("sans", False, 36),
               (40, 40, 40)) + 4
    y = center(d, img, y, "700 mL", font("sans", True, 38), (40, 40, 40)) + 40
    y = center(d, img, y, "PRODUCED & BOTTLED BY DESTILERIA CASA AZUL",
               font("sans", False, 22), terra) + 4
    y = center(d, img, y, "JALISCO - PRODUCT OF MEXICO", font("sans", False, 22),
               terra) + 36
    d.line([(60, y), (W - 60, y)], fill=azul, width=2)
    draw_warning(d, y + 18, W, (40, 40, 40), size=21, wrap_at=62)
    img.save(OUT / "casa_azul_tequila.png")


def velvet_hare():
    W, H = 850, 1000
    burgundy, cream, gold = (74, 20, 36), (243, 235, 220), (198, 160, 90)
    img = Image.new("RGB", (W, H), burgundy)
    d = ImageDraw.Draw(img)
    d.rectangle([26, 26, W - 26, H - 26], outline=gold, width=2)
    d.rectangle([90, 140, W - 90, H - 160], fill=cream)
    d.rectangle([102, 152, W - 102, H - 172], outline=burgundy, width=2)
    cx, cy = W // 2, 260
    d.ellipse([cx - 34, cy - 10, cx + 34, cy + 60], fill=burgundy)
    d.ellipse([cx - 16, cy - 52, cx - 2, cy - 2], fill=burgundy)
    d.ellipse([cx + 2, cy - 56, cx + 16, cy - 6], fill=burgundy)
    y = 350
    y = center(d, img, y, "VELVET HARE", font("serif", True, 76), burgundy) + 2
    y = center(d, img, y, "VINEYARDS", font("serif", False, 34), (120, 90, 60)) + 26
    y = center(d, img, y, "California Red Wine", font("italic", False, 40),
               burgundy) + 22
    y = center(d, img, y, "2023", font("serif", False, 34), (120, 90, 60)) + 40
    y = center(d, img, y, "13.5% Alc. by Vol.  -  750 mL",
               font("serif", False, 32), (60, 40, 40)) + 30
    y = center(d, img, y, "Produced & Bottled by Velvet Hare Vineyards",
               font("serif", False, 24), (100, 70, 60)) + 2
    center(d, img, y, "Sonoma County, California", font("serif", False, 24),
           (100, 70, 60))
    img.save(OUT / "velvet_hare_wine.png")


def photograph(src_path, dst_path, angle_deg=4, glare=False, blur=0.6,
               tilt=0.06):
    label = Image.open(src_path).convert("RGB")
    lw, lh = label.size
    W, H = int(lw * 1.5), int(lh * 1.35)
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for yy in range(H):
        t = yy / H
        d.line([(0, yy), (W, yy)],
               fill=(int(92 - 25 * t), int(66 - 18 * t), int(46 - 12 * t)))

    shift = int(lh * tilt)
    src_quad = [(0, 0), (lw, 0), (lw, lh), (0, lh)]
    dst_quad = [(0, 0), (lw, shift), (lw, lh - shift), (0, lh)]

    def coeffs(pa, pb):
        m = []
        for p1, p2 in zip(pa, pb):
            m.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
            m.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
        target = [c for p in pb for c in p]
        n = 8
        A = [row[:] + [t] for row, t in zip(m, target)]
        for col in range(n):
            piv = max(range(col, n), key=lambda r: abs(A[r][col]))
            A[col], A[piv] = A[piv], A[col]
            for r in range(n):
                if r != col and A[r][col]:
                    f = A[r][col] / A[col][col]
                    A[r] = [a - f * b for a, b in zip(A[r], A[col])]
        return [A[i][n] / A[i][i] for i in range(n)]

    warped = label.transform((lw, lh), Image.PERSPECTIVE,
                             coeffs(dst_quad, src_quad),
                             resample=Image.BICUBIC, fillcolor=(70, 50, 36))
    warped = warped.rotate(angle_deg, expand=True, resample=Image.BICUBIC,
                           fillcolor=(70, 50, 36))

    ox, oy = (W - warped.width) // 2, (H - warped.height) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rectangle([ox + 14, oy + 18, ox + warped.width + 14,
                  oy + warped.height + 18], fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow).convert("RGB")
    bg.paste(warped, (ox, oy))

    img = bg
    if glare:
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gx, gy = int(W * 0.42), int(H * 0.68)
        gd.ellipse([gx - 190, gy - 120, gx + 190, gy + 120],
                   fill=(255, 255, 245, 165))
        gd.ellipse([int(W * 0.6) - 90, int(H * 0.2) - 60,
                    int(W * 0.6) + 90, int(H * 0.2) + 60],
                   fill=(255, 255, 255, 90))
        g = g.filter(ImageFilter.GaussianBlur(38))
        img = Image.alpha_composite(img.convert("RGBA"), g).convert("RGB")

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    noise = Image.effect_noise(img.size, 14).convert("L")
    img = Image.blend(img, Image.merge("RGB", (noise, noise, noise)), 0.05)
    img = ImageEnhance.Contrast(img).enhance(0.97)
    img.save(dst_path)


if __name__ == "__main__":
    midnight_gin()
    sunset_ipa()
    casa_azul()
    velvet_hare()
    photograph(OUT / "old_tom_clean.png", OUT / "old_tom_photo.png",
               angle_deg=1.5, glare=False, blur=0.3, tilt=0.03)
    photograph(OUT / "old_tom_clean.png", OUT / "old_tom_photo_glare.png",
               angle_deg=6, glare=True, blur=1.1, tilt=0.09)
    for n in ["midnight_gin", "sunset_ipa", "casa_azul_tequila",
              "velvet_hare_wine", "old_tom_photo", "old_tom_photo_glare"]:
        print("wrote", OUT / (n + ".png"))

    csv_path = OUT / "applications.csv"
    rows = csv_path.read_text().splitlines() if csv_path.exists() else [
        "image_filename,brand_name,class_type,alcohol_content,net_contents"]
    new = [
        "midnight_gin.png,MIDNIGHT,London Dry Gin,47,750 mL",
        "sunset_ipa.png,SUNSET CANYON,India Pale Ale,6.5,12 fl oz",
        "casa_azul_tequila.png,CASA AZUL,Tequila Reposado,40,750 mL",
        "velvet_hare_wine.png,VELVET HARE,California Red Wine,13.5,750 mL",
        "old_tom_photo.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45,750 mL",
        "old_tom_photo_glare.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45,750 mL",
    ]
    existing = set(r.split(",")[0] for r in rows)
    rows += [r for r in new if r.split(",")[0] not in existing]
    csv_path.write_text("\n".join(rows) + "\n")
    print("updated", csv_path)

