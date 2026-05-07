"""
核动力科研牛马 - 图标生成器
使用 Pillow 直接绘制多尺寸 ICO 图标
"""
from PIL import Image, ImageDraw
import math
import os
import struct
import io


def draw_research_ox_horse(size: int) -> Image.Image:
    """
    绘制科研牛马主题图标。
    设计概念：
    - 牛头卡通形象，戴着圆框眼镜
    - 头顶有原子/核符号，代表"核动力"
    - 手持烧杯，代表科研
    - 背景为深色圆角方形，主体为亮青绿色系
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 配色方案 - 青绿色科技风
    BG_COLOR = (11, 17, 32, 255)
    PRIMARY = (45, 212, 191, 255)
    PRIMARY_DARK = (20, 184, 166, 255)
    ACCENT = (251, 191, 36, 255)
    WHITE = (241, 245, 249, 255)
    LIQUID = (56, 189, 248, 200)

    s = size / 256.0
    margin = int(8 * s)
    bg_rect = [margin, margin, size - margin, size - margin]
    radius = int(48 * s)
    draw.rounded_rectangle(bg_rect, radius=radius, fill=BG_COLOR)
    border_width = max(1, int(3 * s))
    draw.rounded_rectangle(bg_rect, radius=radius, outline=PRIMARY, width=border_width)

    cx, cy = size // 2, size // 2

    # 牛头
    head_w = int(140 * s)
    head_h = int(120 * s)
    head_box = [
        cx - head_w // 2,
        cy - int(10 * s) - head_h // 2,
        cx + head_w // 2,
        cy - int(10 * s) + head_h // 2
    ]
    draw.ellipse(head_box, fill=PRIMARY)

    # 头发
    hair_box = [
        cx - head_w // 2 + int(10 * s),
        cy - int(10 * s) - head_h // 2,
        cx + head_w // 2 - int(10 * s),
        cy - int(10 * s) - head_h // 2 + int(40 * s)
    ]
    draw.ellipse(hair_box, fill=PRIMARY_DARK)

    # 牛角
    horn_w = max(2, int(8 * s))
    draw.line([
        (cx - int(50 * s), cy - int(50 * s)),
        (cx - int(70 * s), cy - int(90 * s)),
        (cx - int(55 * s), cy - int(85 * s)),
    ], fill=ACCENT, width=horn_w, joint="curve")
    draw.line([
        (cx + int(50 * s), cy - int(50 * s)),
        (cx + int(70 * s), cy - int(90 * s)),
        (cx + int(55 * s), cy - int(85 * s)),
    ], fill=ACCENT, width=horn_w, joint="curve")

    # 耳朵
    draw.polygon([
        cx - int(55 * s), cy - int(45 * s),
        cx - int(75 * s), cy - int(75 * s),
        cx - int(45 * s), cy - int(55 * s)
    ], fill=PRIMARY)
    draw.polygon([
        cx + int(55 * s), cy - int(45 * s),
        cx + int(75 * s), cy - int(75 * s),
        cx + int(45 * s), cy - int(55 * s)
    ], fill=PRIMARY)

    # 眼镜
    glass_r = int(22 * s)
    glass_w = max(1, int(3 * s))
    draw.ellipse([
        cx - int(35 * s) - glass_r, cy - int(25 * s) - glass_r,
        cx - int(35 * s) + glass_r, cy - int(25 * s) + glass_r
    ], outline=WHITE, width=glass_w)
    draw.ellipse([
        cx + int(35 * s) - glass_r, cy - int(25 * s) - glass_r,
        cx + int(35 * s) + glass_r, cy - int(25 * s) + glass_r
    ], outline=WHITE, width=glass_w)
    draw.line([
        (cx - int(15 * s), cy - int(25 * s)),
        (cx + int(15 * s), cy - int(25 * s))
    ], fill=WHITE, width=glass_w)

    # 眼睛
    eye_r = max(2, int(5 * s))
    draw.ellipse([
        cx - int(35 * s) - eye_r, cy - int(25 * s) - eye_r,
        cx - int(35 * s) + eye_r, cy - int(25 * s) + eye_r
    ], fill=BG_COLOR)
    draw.ellipse([
        cx + int(35 * s) - eye_r, cy - int(25 * s) - eye_r,
        cx + int(35 * s) + eye_r, cy - int(25 * s) + eye_r
    ], fill=BG_COLOR)

    # 鼻孔
    nose_r = max(2, int(6 * s))
    draw.ellipse([
        cx - int(15 * s) - nose_r, cy + int(15 * s) - nose_r,
        cx - int(15 * s) + nose_r, cy + int(15 * s) + nose_r
    ], fill=PRIMARY_DARK)
    draw.ellipse([
        cx + int(15 * s) - nose_r, cy + int(15 * s) - nose_r,
        cx + int(15 * s) + nose_r, cy + int(15 * s) + nose_r
    ], fill=PRIMARY_DARK)

    # 嘴巴
    mouth_y = cy + int(35 * s)
    draw.arc([
        cx - int(20 * s), mouth_y - int(10 * s),
        cx + int(20 * s), mouth_y + int(10 * s)
    ], start=0, end=180, fill=PRIMARY_DARK, width=max(1, int(2 * s)))

    # 原子符号
    atom_cx = cx
    atom_cy = cy - int(80 * s)
    atom_r = int(18 * s)
    draw.ellipse([
        atom_cx - int(5 * s), atom_cy - int(5 * s),
        atom_cx + int(5 * s), atom_cy + int(5 * s)
    ], fill=ACCENT)
    orbit_w = max(1, int(2 * s))
    for angle in [0, 60, 120]:
        rad = math.radians(angle)
        points = []
        for t in range(0, 360, 5):
            tr = math.radians(t)
            x = atom_cx + int(atom_r * math.cos(tr) * math.cos(rad) - atom_r * 0.4 * math.sin(tr) * math.sin(rad))
            y = atom_cy + int(atom_r * math.cos(tr) * math.sin(rad) + atom_r * 0.4 * math.sin(tr) * math.cos(rad))
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=ACCENT, width=orbit_w)

    # 烧杯
    beaker_cx = cx + int(70 * s)
    beaker_cy = cy + int(50 * s)
    beaker_w = int(30 * s)
    beaker_h = int(40 * s)
    beaker_points = [
        (beaker_cx - beaker_w // 2, beaker_cy - beaker_h // 2),
        (beaker_cx - beaker_w // 2, beaker_cy + beaker_h // 2 - int(5 * s)),
        (beaker_cx - beaker_w // 2 + int(5 * s), beaker_cy + beaker_h // 2),
        (beaker_cx + beaker_w // 2 - int(5 * s), beaker_cy + beaker_h // 2),
        (beaker_cx + beaker_w // 2, beaker_cy + beaker_h // 2 - int(5 * s)),
        (beaker_cx + beaker_w // 2, beaker_cy - beaker_h // 2),
    ]
    draw.polygon(beaker_points, outline=WHITE, width=max(1, int(2 * s)))
    liquid_y = beaker_cy + int(5 * s)
    liquid_points = [
        (beaker_cx - beaker_w // 2 + int(3 * s), liquid_y),
        (beaker_cx - beaker_w // 2 + int(5 * s), beaker_cy + beaker_h // 2 - int(3 * s)),
        (beaker_cx + beaker_w // 2 - int(5 * s), beaker_cy + beaker_h // 2 - int(3 * s)),
        (beaker_cx + beaker_w // 2 - int(3 * s), liquid_y),
    ]
    draw.polygon(liquid_points, fill=LIQUID)
    bubble_r = max(1, int(3 * s))
    draw.ellipse([
        beaker_cx - int(5 * s) - bubble_r, liquid_y - int(5 * s) - bubble_r,
        beaker_cx - int(5 * s) + bubble_r, liquid_y - int(5 * s) + bubble_r
    ], fill=WHITE)
    draw.ellipse([
        beaker_cx + int(3 * s) - bubble_r, liquid_y - int(12 * s) - bubble_r,
        beaker_cx + int(3 * s) + bubble_r, liquid_y - int(12 * s) + bubble_r
    ], fill=WHITE)

    return img


def _png_to_ico_entry(img: Image.Image) -> bytes:
    """将 PNG 图像转换为 ICO 文件中的一个条目（含 PNG 数据）。"""
    # ICO 条目头（16字节）
    width = img.width if img.width < 256 else 0
    height = img.height if img.height < 256 else 0
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()
    color_planes = 1
    bits_per_pixel = 32
    # ICO 条目: width(1) height(1) colors(1) reserved(1) planes(2) bpp(2) size(4) offset(4)
    entry = struct.pack(
        "<BBBBHHII",
        width, height, 0, 0,
        color_planes, bits_per_pixel,
        len(png_data),
        0  # offset 稍后计算
    )
    return entry, png_data


def generate_ico(output_path: str) -> str:
    """生成包含多尺寸的 ICO 文件（使用 PNG 编码的 Vista 格式 ICO）。"""
    sizes = [16, 32, 48, 256]
    images = [draw_research_ox_horse(sz) for sz in sizes]

    entries = []
    png_datas = []
    for img in images:
        entry, png_data = _png_to_ico_entry(img)
        entries.append(entry)
        png_datas.append(png_data)

    num_images = len(entries)
    # ICO 文件头: reserved(2) type(2) count(2)
    header = struct.pack("<HHH", 0, 1, num_images)

    # 计算每个条目的 offset
    header_size = 6
    dir_size = 16 * num_images
    offset = header_size + dir_size
    new_entries = []
    for i, entry in enumerate(entries):
        # 替换 entry 中的 offset（最后4字节）
        new_entry = entry[:12] + struct.pack("<I", offset)
        new_entries.append(new_entry)
        offset += len(png_datas[i])

    with open(output_path, "wb") as f:
        f.write(header)
        for entry in new_entries:
            f.write(entry)
        for png_data in png_datas:
            f.write(png_data)

    return output_path


def generate_svg(output_path: str) -> str:
    """生成 SVG 源文件。"""
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#0B1120"/>
    </linearGradient>
    <linearGradient id="primaryGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#5eead4"/>
      <stop offset="100%" stop-color="#2dd4bf"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- 背景 -->
  <rect x="8" y="8" width="240" height="240" rx="48" fill="url(#bgGrad)" stroke="#2dd4bf" stroke-width="3"/>

  <!-- 牛头部 -->
  <ellipse cx="128" cy="118" rx="70" ry="60" fill="url(#primaryGrad)"/>
  <ellipse cx="128" cy="88" rx="60" ry="30" fill="#14b8a6"/>

  <!-- 牛角 -->
  <path d="M78 68 Q58 28 73 33" stroke="#fbbf24" stroke-width="6" fill="none" stroke-linecap="round"/>
  <path d="M178 68 Q198 28 183 33" stroke="#fbbf24" stroke-width="6" fill="none" stroke-linecap="round"/>

  <!-- 耳朵 -->
  <polygon points="73,73 53,43 83,63" fill="#2dd4bf"/>
  <polygon points="183,73 203,43 173,63" fill="#2dd4bf"/>

  <!-- 眼镜 -->
  <circle cx="93" cy="103" r="22" stroke="#f1f5f9" stroke-width="3" fill="none"/>
  <circle cx="163" cy="103" r="22" stroke="#f1f5f9" stroke-width="3" fill="none"/>
  <line x1="115" y1="103" x2="141" y2="103" stroke="#f1f5f9" stroke-width="3"/>

  <!-- 眼睛 -->
  <circle cx="93" cy="103" r="5" fill="#0B1120"/>
  <circle cx="163" cy="103" r="5" fill="#0B1120"/>

  <!-- 鼻孔 -->
  <ellipse cx="113" cy="133" rx="6" ry="6" fill="#14b8a6"/>
  <ellipse cx="143" cy="133" rx="6" ry="6" fill="#14b8a6"/>

  <!-- 嘴巴 -->
  <path d="M108 153 Q128 168 148 153" stroke="#14b8a6" stroke-width="3" fill="none" stroke-linecap="round"/>

  <!-- 核动力原子符号 -->
  <g transform="translate(128, 38)">
    <circle cx="0" cy="0" r="5" fill="#fbbf24"/>
    <ellipse cx="0" cy="0" rx="18" ry="8" fill="none" stroke="#fbbf24" stroke-width="2" transform="rotate(0)"/>
    <ellipse cx="0" cy="0" rx="18" ry="8" fill="none" stroke="#fbbf24" stroke-width="2" transform="rotate(60)"/>
    <ellipse cx="0" cy="0" rx="18" ry="8" fill="none" stroke="#fbbf24" stroke-width="2" transform="rotate(120)"/>
  </g>

  <!-- 烧杯 -->
  <g transform="translate(198, 168)">
    <polygon points="-15,-20 -15,15 -10,20 10,20 15,15 15,-20" fill="none" stroke="#f1f5f9" stroke-width="2"/>
    <polygon points="-12,0 -10,17 10,17 12,0" fill="#38bdf8" fill-opacity="0.6"/>
    <circle cx="-5" cy="-5" r="3" fill="#f1f5f9"/>
    <circle cx="3" cy="-12" r="3" fill="#f1f5f9"/>
  </g>
</svg>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return output_path


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(base_dir, "nuclear_research_ox.ico")
    svg_path = os.path.join(base_dir, "nuclear_research_ox.svg")

    generate_ico(ico_path)
    generate_svg(svg_path)

    # 验证 ICO 文件
    from PIL import Image
    ico = Image.open(ico_path)
    n = 0
    print("ICO 文件验证:")
    while True:
        try:
            ico.seek(n)
            print(f"  帧 {n}: {ico.size}x{ico.size} {ico.mode}")
            n += 1
        except EOFError:
            break
    print(f"总计: {n} 帧")
    print(f"✅ ICO 图标已生成: {ico_path}")
    print(f"✅ SVG 源文件已生成: {svg_path}")
