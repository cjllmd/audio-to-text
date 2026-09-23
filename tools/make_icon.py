#!/usr/bin/env python3
"""生成应用图标：麦克风 + 声波，输出 PNG / ICO / ICNS"""
import math
import os
import struct
import sys

from PIL import Image, ImageDraw

SIZE = 1024
CX, CY = SIZE // 2, SIZE // 2
BG = (41, 98, 255)
WHITE = (255, 255, 255)


def _ellipse_ring(draw, cx, cy, rx, ry, fill, width=1):
    draw.ellipse(
        [cx - rx, cy - ry, cx + rx, cy + ry],
        fill=fill if width <= 1 else None,
        outline=fill if width > 1 else None,
        width=width,
    )


def draw_icon(size=SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / SIZE

    r_bg = int(460 * s)
    d.ellipse(
        [CX - r_bg, CY - r_bg, CX + r_bg, CY + r_bg],
        fill=(*BG, 255),
    )

    mic_cx = CX
    mic_cy = int(CY - 30 * s)
    head_rx = int(62 * s)
    head_ry = int(90 * s)
    head_top = mic_cy - head_ry
    head_bot = mic_cy + head_ry

    d.rounded_rectangle(
        [mic_cx - head_rx, head_top, mic_cx + head_rx, head_bot],
        radius=int(62 * s),
        fill=WHITE,
    )

    stand_y = head_bot + int(8 * s)
    stand_w = int(10 * s)
    d.rectangle(
        [mic_cx - stand_w, stand_y, mic_cx + stand_w, stand_y + int(50 * s)],
        fill=WHITE,
    )

    base_y = stand_y + int(50 * s)
    arc_rx = int(50 * s)
    d.arc(
        [mic_cx - arc_rx, base_y - int(25 * s), mic_cx + arc_rx, base_y + int(25 * s)],
        start=0,
        end=180,
        fill=WHITE,
        width=int(10 * s),
    )

    for dx, amp in [(-1, 0.85), (1, 0.85)]:
        arc_cx = mic_cx + dx * int(95 * s)
        arc_cy = mic_cy
        arc_rx2 = int(30 * s)
        arc_ry2 = int(75 * s)
        start_a = 90 if dx == -1 else 270
        end_a = 270 if dx == -1 else 90
        d.arc(
            [arc_cx - arc_rx2, arc_cy - arc_ry2, arc_cx + arc_rx2, arc_cy + arc_ry2],
            start=start_a,
            end=end_a,
            fill=WHITE,
            width=int(10 * s),
        )

    wave_base_x = CX + int(180 * s)
    wave_cy = CY
    for i, (h, w) in enumerate([(40, 8), (65, 8), (40, 8)]):
        x = wave_base_x + i * int(28 * s)
        half_h = int(h * s)
        half_w = int(w * s)
        d.rounded_rectangle(
            [x - half_w, wave_cy - half_h, x + half_w, wave_cy + half_h],
            radius=int(4 * s),
            fill=WHITE,
        )

    return img


def png_to_icns(png_path, icns_path):
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    src = Image.open(png_path)
    iconset_dir = png_path + ".iconset"
    os.makedirs(iconset_dir, exist_ok=True)
    for sz in sizes:
        im = src.resize((sz, sz), Image.LANCZOS)
        im.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}.png"))
        if sz * 2 <= 1024:
            im2 = src.resize((sz * 2, sz * 2), Image.LANCZOS)
            im2.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}@2x.png"))
    os.system(f"iconutil -c icns \"{iconset_dir}\" \"{icns_path}\"")
    import shutil
    shutil.rmtree(iconset_dir, ignore_errors=True)


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")
    os.makedirs(out_dir, exist_ok=True)

    img = draw_icon()
    png_path = os.path.join(out_dir, "icon_1024.png")
    img.save(png_path)
    print(f"PNG: {png_path}")

    ico_path = os.path.join(out_dir, "icon.ico")
    ico_sizes = [16, 32, 48, 64, 128, 256]
    ico_images = [img.resize((s, s), Image.LANCZOS) for s in ico_sizes]
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:],
    )
    print(f"ICO: {ico_path}")

    icns_path = os.path.join(out_dir, "icon.icns")
    if sys.platform == "darwin":
        png_to_icns(png_path, icns_path)
        print(f"ICNS: {icns_path}")
    else:
        print("ICNS: 跳过（需在 macOS 上生成）")

    for preview_sz in [64, 256]:
        p = os.path.join(out_dir, f"icon_{preview_sz}.png")
        img.resize((preview_sz, preview_sz), Image.LANCZOS).save(p)
        print(f"预览: {p}")


if __name__ == "__main__":
    main()