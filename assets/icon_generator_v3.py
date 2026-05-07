"""
核动力科研牛马 - 图标生成器 V3
金黄色牛、大角、疲惫神色、戴眼镜、正在操作电脑
"""
from PIL import Image, ImageDraw
import math
import os
import struct
import io


# ── 配色 ──────────────────────────────────────────────────
BG = (11, 17, 32, 255)          # 深蓝黑背景
OX_GOLD = (251, 191, 36, 255)   # 金黄色牛头 #fbbf24
OX_DK = (217, 119, 6, 255)      # 深金黄阴影 #d97706
HORN_GOLD = (245, 158, 11, 255) # 角的颜色 #f59e0b
GLASSES = (241, 245, 249, 255)  # 眼镜白
SCREEN_GLOW = (45, 212, 191, 180)  # 屏幕青光
PC_BODY = (71, 85, 105, 255)    # 电脑深灰
PC_LIGHT = (148, 163, 184, 255) # 电脑亮部
EYE_BAG = (180, 83, 9, 160)     # 黑眼圈
MOUTH_SAD = (120, 53, 15, 255)  # 疲惫嘴色


def draw_ox_v3(size: int) -> Image.Image:
    """V3: 金黄疲惫科研牛马，正在操作电脑。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 256.0

    # ── 背景 ─────────────────────────────────────────────
    m = int(4 * s)
    draw.rounded_rectangle([m, m, size - m, size - m], radius=int(32 * s),
                           fill=BG, outline=(45, 212, 191, 255), width=max(2, int(3 * s)))

    cx, cy = size // 2, size // 2

    # ========== 电脑（在牛前方，先画）==========
    pc_w = int(110 * s)
    pc_h = int(70 * s)
    pc_x = cx - pc_w // 2
    pc_y = cy + int(35 * s)
    # 显示器外壳
    draw.rounded_rectangle([pc_x, pc_y, pc_x + pc_w, pc_y + pc_h],
                           radius=int(6 * s), fill=PC_BODY, outline=PC_LIGHT, width=max(2, int(3 * s)))
    # 屏幕（发光青绿色）
    scr_m = int(6 * s)
    draw.rounded_rectangle([pc_x + scr_m, pc_y + scr_m, pc_x + pc_w - scr_m, pc_y + pc_h - scr_m],
                           radius=int(4 * s), fill=(15, 23, 42, 255), outline=SCREEN_GLOW, width=max(1, int(2 * s)))
    # 屏幕上的代码/公式线条
    line_y = pc_y + scr_m + int(8 * s)
    for i in range(4):
        lw = int((40 + i * 15) * s)
        draw.line([(pc_x + scr_m + int(8 * s), line_y),
                   (pc_x + scr_m + int(8 * s) + lw, line_y)],
                  fill=SCREEN_GLOW, width=max(1, int(2 * s)))
        line_y += int(10 * s)
    # 底座
    stand_w = int(30 * s)
    stand_h = int(10 * s)
    draw.rectangle([cx - stand_w // 2, pc_y + pc_h, cx + stand_w // 2, pc_y + pc_h + stand_h],
                   fill=PC_BODY, outline=PC_LIGHT, width=max(1, int(2 * s)))
    # 键盘（简化横条）
    kb_w = int(80 * s)
    kb_h = int(6 * s)
    draw.rounded_rectangle([cx - kb_w // 2, pc_y + pc_h + stand_h + int(3 * s),
                            cx + kb_w // 2, pc_y + pc_h + stand_h + int(3 * s) + kb_h],
                           radius=int(2 * s), fill=PC_BODY, outline=PC_LIGHT, width=max(1, int(2 * s)))

    # ========== 牛手（在键盘上方）==========
    # 左手
    draw.ellipse([cx - int(35 * s), pc_y + pc_h + stand_h - int(5 * s),
                  cx - int(15 * s), pc_y + pc_h + stand_h + int(10 * s)], fill=OX_GOLD, outline=OX_DK, width=max(1, int(2 * s)))
    # 右手
    draw.ellipse([cx + int(15 * s), pc_y + pc_h + stand_h - int(5 * s),
                  cx + int(35 * s), pc_y + pc_h + stand_h + int(10 * s)], fill=OX_GOLD, outline=OX_DK, width=max(1, int(2 * s)))

    # ========== 牛头（金黄色）==========
    head_rx = int(72 * s)
    head_ry = int(58 * s)
    head_cy = cy - int(25 * s)
    # 白色描边让牛头更突出
    ow = max(2, int(4 * s))
    draw.ellipse([cx - head_rx, head_cy - head_ry, cx + head_rx, head_cy + head_ry],
                 fill=OX_GOLD, outline=WHITE, width=ow)

    # 头顶深色（头发/阴影）
    draw.ellipse([cx - head_rx + int(6 * s), head_cy - head_ry,
                  cx + head_rx - int(6 * s), head_cy - head_ry + int(30 * s)],
                 fill=HORN_GOLD)

    # ========== 大角（三角锥形状）==========
    # 左角 - 三角锥：底部宽，向上收尖
    draw.polygon([
        (cx - int(55 * s), head_cy - int(25 * s)),   # 底部左侧（连接头部）
        (cx - int(30 * s), head_cy - int(40 * s)),   # 底部右侧（连接头部）
        (cx - int(75 * s), head_cy - int(85 * s)),   # 顶尖
    ], fill=HORN_GOLD, outline=OX_DK, width=max(2, int(3 * s)))
    # 右角
    draw.polygon([
        (cx + int(55 * s), head_cy - int(25 * s)),   # 底部右侧
        (cx + int(30 * s), head_cy - int(40 * s)),   # 底部左侧
        (cx + int(75 * s), head_cy - int(85 * s)),   # 顶尖
    ], fill=HORN_GOLD, outline=OX_DK, width=max(2, int(3 * s)))

    # ========== 耳朵 ==========
    draw.polygon([
        (cx - int(55 * s), head_cy - int(35 * s)),
        (cx - int(72 * s), head_cy - int(60 * s)),
        (cx - int(40 * s), head_cy - int(45 * s)),
    ], fill=OX_GOLD, outline=OX_DK, width=max(1, int(2 * s)))
    draw.polygon([
        (cx + int(55 * s), head_cy - int(35 * s)),
        (cx + int(72 * s), head_cy - int(60 * s)),
        (cx + int(40 * s), head_cy - int(45 * s)),
    ], fill=OX_GOLD, outline=OX_DK, width=max(1, int(2 * s)))

    # ========== 疲惫神色 ==========
    # 黑眼圈（半透暗色椭圆在眼睛下方）
    bag_r = int(18 * s)
    bag_y = head_cy - int(5 * s)
    bag_offset = int(32 * s)
    draw.ellipse([cx - bag_offset - bag_r, bag_y - int(5 * s),
                  cx - bag_offset + bag_r, bag_y + int(15 * s)], fill=EYE_BAG)
    draw.ellipse([cx + bag_offset - bag_r, bag_y - int(5 * s),
                  cx + bag_offset + bag_r, bag_y + int(15 * s)], fill=EYE_BAG)

    # ========== 眼镜（大圆框）==========
    glass_r = int(24 * s)
    glass_w = max(2, int(4 * s))
    glass_y = head_cy - int(8 * s)
    go = int(34 * s)
    # 左镜片
    draw.ellipse([cx - go - glass_r, glass_y - glass_r,
                  cx - go + glass_r, glass_y + glass_r],
                 outline=GLASSES, width=glass_w)
    # 右镜片
    draw.ellipse([cx + go - glass_r, glass_y - glass_r,
                  cx + go + glass_r, glass_y + glass_r],
                 outline=GLASSES, width=glass_w)
    # 鼻梁
    draw.line([(cx - go + glass_r, glass_y), (cx + go - glass_r, glass_y)],
              fill=GLASSES, width=glass_w)
    # 镜腿
    draw.line([(cx - go - glass_r, glass_y), (cx - head_rx + int(3 * s), glass_y - int(3 * s))],
              fill=GLASSES, width=max(1, int(2 * s)))
    draw.line([(cx + go + glass_r, glass_y), (cx + head_rx - int(3 * s), glass_y - int(3 * s))],
              fill=GLASSES, width=max(1, int(2 * s)))

    # ========== 眼睛（半闭的疲惫眼）==========
    eye_r = max(3, int(6 * s))
    # 左眼 - 半闭（用弧线代替完整圆）
    draw.arc([cx - go - eye_r, glass_y - eye_r, cx - go + eye_r, glass_y + eye_r],
             start=10, end=170, fill=BG, width=max(2, int(4 * s)))
    # 右眼
    draw.arc([cx + go - eye_r, glass_y - eye_r, cx + go + eye_r, glass_y + eye_r],
             start=10, end=170, fill=BG, width=max(2, int(4 * s)))

    # ========== 鼻孔 ==========
    nr = max(2, int(6 * s))
    ny = head_cy + int(18 * s)
    draw.ellipse([cx - int(14 * s) - nr, ny - nr, cx - int(14 * s) + nr, ny + nr], fill=OX_DK)
    draw.ellipse([cx + int(14 * s) - nr, ny - nr, cx + int(14 * s) + nr, ny + nr], fill=OX_DK)

    # ========== 疲惫的嘴（下弯弧线）==========
    mw = int(18 * s)
    mh = int(8 * s)
    my = head_cy + int(35 * s)
    # 倒过来的微笑 = 疲惫/悲伤
    draw.arc([cx - mw, my - mh, cx + mw, my + mh],
             start=190, end=350, fill=MOUTH_SAD, width=max(2, int(3 * s)))

    return img


WHITE = (255, 255, 255, 255)


def _build_ico(images: list, output_path: str):
    """手动构建 Vista 格式 PNG-in-ICO。"""
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
    offset = 6 + 16 * len(entries)
    new_entries = []
    for i, entry in enumerate(entries):
        new_entry = entry[:12] + struct.pack("<I", offset)
        new_entries.append(new_entry)
        offset += len(png_datas[i])

    with open(output_path, "wb") as f:
        f.write(header)
        for e in new_entries:
            f.write(e)
        for d in png_datas:
            f.write(d)


def generate_ico(output_path: str) -> str:
    sizes = [16, 32, 48, 256]
    images = [draw_ox_v3(sz) for sz in sizes]
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
  </defs>
  <rect x="4" y="4" width="248" height="248" rx="32" fill="url(#bg)" stroke="#2dd4bf" stroke-width="3"/>

  <!-- 电脑显示器 -->
  <rect x="73" y="138" width="110" height="70" rx="6" fill="#475569" stroke="#94a3b8" stroke-width="3"/>
  <rect x="81" y="146" width="94" height="54" rx="4" fill="#0f172a" stroke="#2dd4bf" stroke-width="2"/>
  <line x1="89" y1="156" x2="140" y2="156" stroke="#2dd4bf" stroke-width="2"/>
  <line x1="89" y1="168" x2="155" y2="168" stroke="#2dd4bf" stroke-width="2"/>
  <line x1="89" y1="180" x2="130" y2="180" stroke="#2dd4bf" stroke-width="2"/>
  <rect x="113" y="208" width="30" height="10" fill="#475569" stroke="#94a3b8" stroke-width="2"/>
  <rect x="88" y="221" width="80" height="6" rx="2" fill="#475569" stroke="#94a3b8" stroke-width="1"/>

  <!-- 牛手 -->
  <ellipse cx="93" cy="208" rx="10" ry="8" fill="#fbbf24" stroke="#d97706" stroke-width="2"/>
  <ellipse cx="163" cy="208" rx="10" ry="8" fill="#fbbf24" stroke="#d97706" stroke-width="2"/>

  <!-- 牛头 -->
  <ellipse cx="128" cy="98" rx="72" ry="58" fill="#fbbf24" stroke="#ffffff" stroke-width="4"/>
  <ellipse cx="128" cy="73" rx="66" ry="26" fill="#f59e0b"/>

  <!-- 大角 -->
  <!-- 三角锥大角 -->
  <polygon points="73,73 98,58 48,28" fill="#f59e0b" stroke="#d97706" stroke-width="3"/>
  <polygon points="183,73 158,58 208,28" fill="#f59e0b" stroke="#d97706" stroke-width="3"/>

  <!-- 耳朵 -->
  <polygon points="73,63 56,38 88,53" fill="#fbbf24" stroke="#d97706" stroke-width="2"/>
  <polygon points="183,63 200,38 168,53" fill="#fbbf24" stroke="#d97706" stroke-width="2"/>

  <!-- 黑眼圈 -->
  <ellipse cx="94" cy="93" rx="18" ry="12" fill="#b45309" fill-opacity="0.6"/>
  <ellipse cx="162" cy="93" rx="18" ry="12" fill="#b45309" fill-opacity="0.6"/>

  <!-- 眼镜 -->
  <circle cx="94" cy="90" r="24" stroke="#f1f5f9" stroke-width="4" fill="none"/>
  <circle cx="162" cy="90" r="24" stroke="#f1f5f9" stroke-width="4" fill="none"/>
  <line x1="118" y1="90" x2="138" y2="90" stroke="#f1f5f9" stroke-width="4"/>
  <line x1="70" y1="90" x2="56" y2="87" stroke="#f1f5f9" stroke-width="2"/>
  <line x1="186" y1="90" x2="200" y2="87" stroke="#f1f5f9" stroke-width="2"/>

  <!-- 半闭疲惫眼 -->
  <path d="M88 90 Q94 84 100 90" stroke="#0B1120" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path d="M156 90 Q162 84 168 90" stroke="#0B1120" stroke-width="4" fill="none" stroke-linecap="round"/>

  <!-- 鼻孔 -->
  <ellipse cx="114" cy="116" rx="6" ry="6" fill="#d97706"/>
  <ellipse cx="142" cy="116" rx="6" ry="6" fill="#d97706"/>

  <!-- 疲惫下弯嘴 -->
  <path d="M110 133 Q128 125 146 133" stroke="#78350f" stroke-width="3" fill="none" stroke-linecap="round"/>
</svg>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return output_path


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    ico = os.path.join(base, "nuclear_research_ox.ico")
    svg = os.path.join(base, "nuclear_research_ox.svg")
    generate_ico(ico)
    generate_svg(svg)
    # 验证
    with open(ico, "rb") as f:
        data = f.read()
    _, _, count = struct.unpack("<HHH", data[:6])
    print(f"ICO: {count} 帧")
    off = 6
    for i in range(count):
        w, h, _, _, _, bpp, sz, ofs = struct.unpack("<BBBBHHII", data[off:off + 16])
        print(f"  {w if w else 256}x{h if h else 256} {bpp}bpp {sz}B")
        off += 16
    print(f"✅ ICO: {ico}")
    print(f"✅ SVG: {svg}")
