"""
核动力科研牛马 - 图标生成器 V2
重新设计：更低抽象度、更高辨识度、更清晰锐利
"""
from PIL import Image, ImageDraw
import math
import os
import struct
import io


# ── 配色方案 ──────────────────────────────────────────────
BG = (11, 17, 32, 255)          # 深蓝黑背景
PRIMARY = (45, 212, 191, 255)   # 青绿主色 #2dd4bf
PRIMARY_DK = (20, 184, 166, 255)  # 深青绿 #14b8a6
ACCENT = (251, 191, 36, 255)    # 金色 #fbbf24
WHITE = (255, 255, 255, 255)    # 纯白
LIQUID = (56, 189, 248, 230)    # 浅蓝液体
GLASS = (255, 255, 255, 180)    # 玻璃反光


def draw_circle(draw, cx, cy, r, fill=None, outline=None, width=1):
    """辅助：绘制圆。"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=width)


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """辅助：绘制圆角矩形。"""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_research_ox_horse_v2(size: int) -> Image.Image:
    """
    V2 设计：
    - 更大的牛头占比（约占画面 60%）
    - 更粗的线条和更大的元素
    - 牛角用实心三角形而非细线
    - 原子符号简化为中心圆 + 三条粗椭圆轨道
    - 烧杯更大，液体和气泡更明显
    - 增加白色描边提升辨识度
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 256.0

    # ── 背景 ─────────────────────────────────────────────
    margin = int(6 * s)
    pad = margin
    bg_rect = [pad, pad, size - pad, size - pad]
    r_bg = int(40 * s)
    # 外发光边框
    glow_w = max(2, int(4 * s))
    draw_rounded_rect(draw, bg_rect, r_bg, fill=BG, outline=PRIMARY, width=glow_w)

    cx, cy = size // 2, size // 2

    # ── 牛角（实心三角形，金色）─────────────────────────
    horn_h = int(35 * s)
    horn_w = int(22 * s)
    # 左角
    draw.polygon([
        (cx - int(45 * s), cy - int(35 * s)),
        (cx - int(65 * s), cy - int(70 * s)),
        (cx - int(30 * s), cy - int(50 * s)),
    ], fill=ACCENT)
    # 右角
    draw.polygon([
        (cx + int(45 * s), cy - int(35 * s)),
        (cx + int(65 * s), cy - int(70 * s)),
        (cx + int(30 * s), cy - int(50 * s)),
    ], fill=ACCENT)

    # ── 耳朵（实心三角形）───────────────────────────────
    ear_h = int(28 * s)
    ear_w = int(18 * s)
    draw.polygon([
        (cx - int(50 * s), cy - int(40 * s)),
        (cx - int(68 * s), cy - int(65 * s)),
        (cx - int(35 * s), cy - int(48 * s)),
    ], fill=PRIMARY)
    draw.polygon([
        (cx + int(50 * s), cy - int(40 * s)),
        (cx + int(68 * s), cy - int(65 * s)),
        (cx + int(35 * s), cy - int(48 * s)),
    ], fill=PRIMARY)

    # ── 牛头（大椭圆，占画面主体）───────────────────────
    head_rx = int(75 * s)
    head_ry = int(65 * s)
    head_cy = cy - int(5 * s)
    # 白色描边让牛头更突出
    outline_w = max(2, int(4 * s))
    draw.ellipse(
        [cx - head_rx, head_cy - head_ry, cx + head_rx, head_cy + head_ry],
        fill=PRIMARY, outline=WHITE, width=outline_w
    )

    # ── 头顶深色区域（头发/鬃毛）────────────────────────
    hair_ry = int(28 * s)
    draw.ellipse(
        [cx - head_rx + int(8 * s), head_cy - head_ry,
         cx + head_rx - int(8 * s), head_cy - head_ry + hair_ry * 2],
        fill=PRIMARY_DK
    )

    # ── 圆框眼镜（粗白框，大镜片）───────────────────────
    glass_r = int(26 * s)
    glass_w = max(2, int(4 * s))
    glass_y = head_cy - int(8 * s)
    glass_offset = int(38 * s)
    # 左镜片
    draw_circle(draw, cx - glass_offset, glass_y, glass_r,
                outline=WHITE, width=glass_w)
    # 右镜片
    draw_circle(draw, cx + glass_offset, glass_y, glass_r,
                outline=WHITE, width=glass_w)
    # 鼻梁架
    draw.line([
        (cx - glass_offset + glass_r, glass_y),
        (cx + glass_offset - glass_r, glass_y)
    ], fill=WHITE, width=glass_w)
    # 镜腿
    draw.line([
        (cx - glass_offset - glass_r, glass_y),
        (cx - head_rx + int(5 * s), glass_y - int(5 * s))
    ], fill=WHITE, width=max(1, int(2 * s)))
    draw.line([
        (cx + glass_offset + glass_r, glass_y),
        (cx + head_rx - int(5 * s), glass_y - int(5 * s))
    ], fill=WHITE, width=max(1, int(2 * s)))

    # ── 眼睛（黑色实心圆，带白色高光点）─────────────────
    eye_r = max(3, int(7 * s))
    eye_y = glass_y
    # 左眼
    draw_circle(draw, cx - glass_offset, eye_y, eye_r, fill=BG)
    draw_circle(draw, cx - glass_offset + int(2 * s), eye_y - int(2 * s), max(1, int(2 * s)), fill=WHITE)
    # 右眼
    draw_circle(draw, cx + glass_offset, eye_y, eye_r, fill=BG)
    draw_circle(draw, cx + glass_offset + int(2 * s), eye_y - int(2 * s), max(1, int(2 * s)), fill=WHITE)

    # ── 鼻孔（深色椭圆）─────────────────────────────────
    nose_rx = max(3, int(8 * s))
    nose_ry = max(2, int(6 * s))
    nose_y = head_cy + int(22 * s)
    draw.ellipse([cx - int(18 * s) - nose_rx, nose_y - nose_ry,
                  cx - int(18 * s) + nose_rx, nose_y + nose_ry], fill=PRIMARY_DK)
    draw.ellipse([cx + int(18 * s) - nose_rx, nose_y - nose_ry,
                  cx + int(18 * s) + nose_rx, nose_y + nose_ry], fill=PRIMARY_DK)

    # ── 嘴巴（微笑弧线）─────────────────────────────────
    mouth_y = head_cy + int(40 * s)
    mw = int(22 * s)
    mh = int(10 * s)
    draw.arc([cx - mw, mouth_y - mh, cx + mw, mouth_y + mh],
             start=10, end=170, fill=PRIMARY_DK, width=max(2, int(3 * s)))

    # ── 核动力原子符号（头顶，更大更醒目）───────────────
    atom_cy = head_cy - head_ry - int(18 * s)
    atom_r = int(22 * s)
    # 中心核（实心金色圆）
    draw_circle(draw, cx, atom_cy, int(7 * s), fill=ACCENT, outline=WHITE, width=max(1, int(2 * s)))
    # 三条粗轨道
    orbit_w = max(2, int(4 * s))
    for angle in [0, 60, 120]:
        rad = math.radians(angle)
        points = []
        for t in range(0, 360, 3):
            tr = math.radians(t)
            # 椭圆参数方程
            x = cx + int(atom_r * math.cos(tr) * math.cos(rad) - atom_r * 0.35 * math.sin(tr) * math.sin(rad))
            y = atom_cy + int(atom_r * math.cos(tr) * math.sin(rad) + atom_r * 0.35 * math.sin(tr) * math.cos(rad))
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=ACCENT, width=orbit_w)

    # ── 手持烧杯（右下角，更大更清晰）───────────────────
    beaker_cx = cx + int(85 * s)
    beaker_cy = cy + int(55 * s)
    bw = int(36 * s)
    bh = int(48 * s)
    bw2 = bw // 2
    # 烧杯外轮廓（白色粗线）
    beaker_pts = [
        (beaker_cx - bw2, beaker_cy - bh // 2),
        (beaker_cx - bw2, beaker_cy + bh // 2 - int(6 * s)),
        (beaker_cx - bw2 + int(6 * s), beaker_cy + bh // 2),
        (beaker_cx + bw2 - int(6 * s), beaker_cy + bh // 2),
        (beaker_cx + bw2, beaker_cy + bh // 2 - int(6 * s)),
        (beaker_cx + bw2, beaker_cy - bh // 2),
    ]
    draw.polygon(beaker_pts, outline=WHITE, width=max(2, int(3 * s)))
    # 烧杯口
    draw.line([
        (beaker_cx - bw2 - int(3 * s), beaker_cy - bh // 2),
        (beaker_cx + bw2 + int(3 * s), beaker_cy - bh // 2)
    ], fill=WHITE, width=max(2, int(3 * s)))
    # 液体（浅蓝色填充）
    liquid_y = beaker_cy + int(8 * s)
    liquid_pts = [
        (beaker_cx - bw2 + int(3 * s), liquid_y),
        (beaker_cx - bw2 + int(6 * s), beaker_cy + bh // 2 - int(4 * s)),
        (beaker_cx + bw2 - int(6 * s), beaker_cy + bh // 2 - int(4 * s)),
        (beaker_cx + bw2 - int(3 * s), liquid_y),
    ]
    draw.polygon(liquid_pts, fill=LIQUID)
    # 液体表面线
    draw.line([
        (beaker_cx - bw2 + int(3 * s), liquid_y),
        (beaker_cx + bw2 - int(3 * s), liquid_y)
    ], fill=WHITE, width=max(1, int(2 * s)))
    # 气泡（白色实心圆）
    b1r = max(2, int(5 * s))
    b2r = max(2, int(4 * s))
    b3r = max(1, int(3 * s))
    draw_circle(draw, beaker_cx - int(6 * s), liquid_y - int(8 * s), b1r, fill=WHITE)
    draw_circle(draw, beaker_cx + int(4 * s), liquid_y - int(18 * s), b2r, fill=WHITE)
    draw_circle(draw, beaker_cx - int(2 * s), liquid_y - int(28 * s), b3r, fill=WHITE)

    return img


def _build_ico(images: list, output_path: str):
    """手动构建 Vista 格式 PNG-in-ICO 文件。"""
    entries = []
    png_datas = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()
        w = img.width if img.width < 256 else 0
        h = img.height if img.height < 256 else 0
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_data), 0)
        entries.append(entry)
        png_datas.append(png_data)

    header = struct.pack("<HHH", 0, 1, len(entries))
    header_size = 6
    dir_size = 16 * len(entries)
    offset = header_size + dir_size
    new_entries = []
    for i, entry in enumerate(entries):
        new_entry = entry[:12] + struct.pack("<I", offset)
        new_entries.append(new_entry)
        offset += len(png_datas[i])

    with open(output_path, "wb") as f:
        f.write(header)
        for entry in new_entries:
            f.write(entry)
        for png_data in png_datas:
            f.write(png_data)


def generate_ico(output_path: str) -> str:
    sizes = [16, 32, 48, 256]
    images = [draw_research_ox_horse_v2(sz) for sz in sizes]
    _build_ico(images, output_path)
    return output_path


def generate_svg(output_path: str) -> str:
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#0B1120"/>
    </linearGradient>
    <linearGradient id="head" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#5eead4"/>
      <stop offset="100%" stop-color="#2dd4bf"/>
    </linearGradient>
  </defs>

  <!-- 背景 -->
  <rect x="6" y="6" width="244" height="244" rx="40" fill="url(#bg)" stroke="#2dd4bf" stroke-width="4"/>

  <!-- 牛角 -->
  <polygon points="83,121 63,86 98,106" fill="#fbbf24"/>
  <polygon points="173,121 193,86 158,106" fill="#fbbf24"/>

  <!-- 耳朵 -->
  <polygon points="78,116 60,91 93,108" fill="#2dd4bf"/>
  <polygon points="178,116 196,91 163,108" fill="#2dd4bf"/>

  <!-- 牛头 -->
  <ellipse cx="128" cy="123" rx="75" ry="65" fill="url(#head)" stroke="#ffffff" stroke-width="4"/>
  <ellipse cx="128" cy="98" rx="67" ry="28" fill="#14b8a6"/>

  <!-- 眼镜 -->
  <circle cx="90" cy="115" r="26" stroke="#ffffff" stroke-width="4" fill="none"/>
  <circle cx="166" cy="115" r="26" stroke="#ffffff" stroke-width="4" fill="none"/>
  <line x1="116" y1="115" x2="140" y2="115" stroke="#ffffff" stroke-width="4"/>
  <line x1="64" y1="115" x2="53" y2="110" stroke="#ffffff" stroke-width="2"/>
  <line x1="192" y1="115" x2="203" y2="110" stroke="#ffffff" stroke-width="2"/>

  <!-- 眼睛 -->
  <circle cx="90" cy="115" r="7" fill="#0B1120"/>
  <circle cx="92" cy="113" r="2" fill="#ffffff"/>
  <circle cx="166" cy="115" r="7" fill="#0B1120"/>
  <circle cx="168" cy="113" r="2" fill="#ffffff"/>

  <!-- 鼻孔 -->
  <ellipse cx="110" cy="145" rx="8" ry="6" fill="#14b8a6"/>
  <ellipse cx="146" cy="145" rx="8" ry="6" fill="#14b8a6"/>

  <!-- 嘴巴 -->
  <path d="M106 158 Q128 173 150 158" stroke="#14b8a6" stroke-width="3" fill="none" stroke-linecap="round"/>

  <!-- 核动力原子 -->
  <g transform="translate(128, 40)">
    <circle cx="0" cy="0" r="7" fill="#fbbf24" stroke="#ffffff" stroke-width="2"/>
    <ellipse cx="0" cy="0" rx="22" ry="8" fill="none" stroke="#fbbf24" stroke-width="4" transform="rotate(0)"/>
    <ellipse cx="0" cy="0" rx="22" ry="8" fill="none" stroke="#fbbf24" stroke-width="4" transform="rotate(60)"/>
    <ellipse cx="0" cy="0" rx="22" ry="8" fill="none" stroke="#fbbf24" stroke-width="4" transform="rotate(120)"/>
  </g>

  <!-- 烧杯 -->
  <g transform="translate(213, 183)">
    <!-- 杯口 -->
    <line x1="-21" y1="-24" x2="21" y2="-24" stroke="#ffffff" stroke-width="3"/>
    <!-- 杯身 -->
    <polygon points="-18,-24 -18,15 -12,24 12,24 18,15 18,-24" fill="none" stroke="#ffffff" stroke-width="3"/>
    <!-- 液体 -->
    <polygon points="-15,0 -12,21 12,21 15,0" fill="#38bdf6" fill-opacity="0.7"/>
    <line x1="-15" y1="0" x2="15" y2="0" stroke="#ffffff" stroke-width="2"/>
    <!-- 气泡 -->
    <circle cx="-6" cy="-8" r="5" fill="#ffffff"/>
    <circle cx="4" cy="-18" r="4" fill="#ffffff"/>
    <circle cx="-2" cy="-28" r="3" fill="#ffffff"/>
  </g>
</svg>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return output_path


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(base, "nuclear_research_ox.ico")
    svg_path = os.path.join(base, "nuclear_research_ox.svg")

    generate_ico(ico_path)
    generate_svg(svg_path)

    # 验证
    with open(ico_path, "rb") as f:
        data = f.read()
    _, _, count = struct.unpack("<HHH", data[:6])
    print(f"ICO 验证: {count} 帧")
    off = 6
    for i in range(count):
        w, h, _, _, _, bpp, sz, ofs = struct.unpack("<BBBBHHII", data[off:off + 16])
        print(f"  帧 {i}: {w if w else 256}x{h if h else 256}, {bpp}bpp, {sz} bytes")
        off += 16
    print(f"✅ ICO: {ico_path}")
    print(f"✅ SVG: {svg_path}")
