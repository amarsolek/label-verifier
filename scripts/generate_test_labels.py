"""Generate synthetic test label images with PIL.

Produces four labels in ../test_labels/ plus applications.csv for batch mode:
  1. old_tom_clean.png        — everything correct → should pass
  2. old_tom_wrong_abv.png    — label says 40%/80 proof, application says 45 → mismatch
  3. stones_throw_case.png    — brand in caps vs title case on application → match w/ note
  4. riverbend_bad_warning.png— 'Government Warning:' in title case + reworded → mismatch

Run:  python scripts/generate_test_labels.py
"""

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "test_labels"
OUT.mkdir(exist_ok=True)

W, H = 900, 1000
CREAM = (247, 242, 230)
INK = (30, 28, 24)

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts"]


def font(bold: bool, size: int, serif=True):
    names = (["DejaVuSerif-Bold.ttf", "timesbd.ttf"] if bold and serif else
             ["DejaVuSerif.ttf", "times.ttf"] if serif else
             ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else
             ["DejaVuSans.ttf", "arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


WARNING_OK = ("GOVERNMENT WARNING:", " (1) According to the Surgeon General, "
              "women should not drink alcoholic beverages during pregnancy "
              "because of the risk of birth defects. (2) Consumption of "
              "alcoholic beverages impairs your ability to drive a car or "
              "operate machinery, and may cause health problems.")

# Title-case prefix AND reworded body ("birth defects" -> "health issues").
WARNING_BAD = ("Government Warning:", " (1) According to the Surgeon General, "
               "women should not drink alcoholic beverages during pregnancy "
               "because of the risk of health issues. (2) Consumption of "
               "alcoholic beverages impairs your ability to drive a car or "
               "operate machinery, and may cause health problems.")


def center(draw, y, text, f, fill=INK, tracking=0):
    w = draw.textlength(text, font=f)
    draw.text(((W - w) / 2, y), text, font=f, fill=fill)
    bbox = f.getbbox(text)
    return y + (bbox[3] - bbox[1]) + 8


def draw_warning(draw, y, prefix, body, bold_prefix=True):
    f_bold = font(True, 22, serif=False)
    f_reg = font(False, 22, serif=False)
    f_prefix = f_bold if bold_prefix else f_reg
    full = prefix + body
    lines = wrap(full, width=62)
    x_margin = 70
    consumed_prefix = 0
    for line in lines:
        x = x_margin
        # Render the prefix portion (possibly split across the first line) bold.
        if consumed_prefix < len(prefix):
            take = min(len(line), len(prefix) - consumed_prefix)
            head, tail = line[:take], line[take:]
            draw.text((x, y), head, font=f_prefix, fill=INK)
            x += draw.textlength(head, font=f_prefix)
            consumed_prefix += take
            draw.text((x, y), tail, font=f_reg, fill=INK)
        else:
            draw.text((x, y), line, font=f_reg, fill=INK)
        y += 30
    return y


def make_label(path, brand, class_lines, abv, contents, producer,
               warning=WARNING_OK, bold_prefix=True, brand_size=64):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    # double border
    d.rectangle([20, 20, W - 20, H - 20], outline=INK, width=4)
    d.rectangle([34, 34, W - 34, H - 34], outline=INK, width=2)

    y = 80
    y = center(d, y, "*   *   *", font(False, 30)) + 10
    y = center(d, y, brand, font(True, brand_size)) + 6
    d.line([(W // 2 - 180, y + 8), (W // 2 + 180, y + 8)], fill=INK, width=3)
    y += 40
    for line in class_lines:
        y = center(d, y, line, font(False, 40)) + 4
    y += 30
    y = center(d, y, abv, font(False, 34)) + 6
    y = center(d, y, contents, font(True, 34)) + 40
    y = center(d, y, producer, font(False, 24)) + 4
    y = center(d, y, "PRODUCT OF USA", font(False, 22)) + 60

    # rule above warning
    d.line([(70, y), (W - 70, y)], fill=INK, width=2)
    y += 20
    draw_warning(d, y, warning[0], warning[1], bold_prefix)

    img.save(path)
    print("wrote", path)


make_label(
    OUT / "old_tom_clean.png",
    "OLD TOM DISTILLERY",
    ["Kentucky Straight", "Bourbon Whiskey"],
    "45% Alc./Vol. (90 Proof)", "750 mL",
    "Distilled & Bottled by Old Tom Distillery Co., Bardstown, KY",
)

make_label(
    OUT / "old_tom_wrong_abv.png",
    "OLD TOM DISTILLERY",
    ["Kentucky Straight", "Bourbon Whiskey"],
    "40% Alc./Vol. (80 Proof)", "750 mL",
    "Distilled & Bottled by Old Tom Distillery Co., Bardstown, KY",
)

make_label(
    OUT / "stones_throw_case.png",
    "STONE'S THROW",   # application says: Stone's Throw
    ["Small Batch", "Rye Whiskey"],
    "46.5% Alc./Vol. (93 Proof)", "750 mL",
    "Bottled by Stone's Throw Spirits, Portland, OR",
    brand_size=72,
)

make_label(
    OUT / "riverbend_bad_warning.png",
    "RIVERBEND",
    ["California", "Red Wine"],
    "13.5% Alc. by Vol.", "750 mL",
    "Produced & Bottled by Riverbend Cellars, Napa, CA",
    warning=WARNING_BAD, bold_prefix=False,
)

csv_path = OUT / "applications.csv"
csv_path.write_text(
    "image_filename,brand_name,class_type,alcohol_content,net_contents\n"
    "old_tom_clean.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45,750 mL\n"
    "old_tom_wrong_abv.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45,750 mL\n"
    "stones_throw_case.png,Stone's Throw,Small Batch Rye Whiskey,46.5,750 mL\n"
    "riverbend_bad_warning.png,RIVERBEND,California Red Wine,13.5,750 mL\n"
)
print("wrote", csv_path)
