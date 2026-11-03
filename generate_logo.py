"""Downmax logo generator. Run:  python generate_logo.py
Creates assets/logo.png, assets/icon.ico and assets/banner.png"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)
S = 1024  # supersampled canvas


def gradient(size, c1, c2):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def make_logo():
    bg = gradient(S, (99, 102, 241), (6, 182, 212))  # indigo -> cyan
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=230, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)

    # soft shadow for arrow
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    white = (255, 255, 255, 255)

    def draw_arrow(d, color, dy=0):
        # shaft
        d.rounded_rectangle((452, 200 + dy, 572, 560 + dy), radius=40, fill=color)
        # head
        d.polygon([(270, 520 + dy), (754, 520 + dy), (512, 770 + dy)], fill=color)
        # tray
        d.rounded_rectangle((230, 800 + dy, 794, 860 + dy), radius=30, fill=color)
        d.rounded_rectangle((230, 740 + dy, 290, 860 + dy), radius=30, fill=color)
        d.rounded_rectangle((734, 740 + dy, 794, 860 + dy), radius=30, fill=color)

    draw_arrow(sd, (0, 0, 0, 90), dy=22)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    icon = Image.alpha_composite(icon, shadow)
    draw_arrow(ImageDraw.Draw(icon), white)
    return icon.resize((512, 512), Image.LANCZOS)


def find_font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    logo = make_logo()
    logo.save(OUT / "logo.png")
    logo.save(OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    banner = Image.new("RGBA", (1200, 360), (15, 23, 42, 255))
    banner.paste(logo.resize((240, 240), Image.LANCZOS), (80, 60), logo.resize((240, 240), Image.LANCZOS))
    d = ImageDraw.Draw(banner)
    d.text((360, 80), "Downmax", font=find_font(110), fill=(255, 255, 255))
    d.text((366, 215), "Download videos & MP3 from any link", font=find_font(38), fill=(148, 163, 184))
    banner.convert("RGB").save(OUT / "banner.png")
    print("Logo files created in", OUT)


if __name__ == "__main__":
    main()
