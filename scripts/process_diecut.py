"""
纸艺刀模裁切与图像处理引擎（Birthday Pop-up Card Skill 核心工具）

通俗用途说明：
1. 把 AI 重绘出来的“白底插画”精准抠掉外部纯白背景，同时 100% 保护人物的白衬衫、眼白、咖啡奶泡和蛋糕白奶油不被误抠。
2. 自动围绕主体轮廓外扩生成一圈圆润的 300g 米白水彩卡纸“刀模白边”与轻微纸边压痕，还原真实手工立体纸片质感。
3. 自动扫描蛋糕立牌顶端找到蜡烛顶芯百分比位置，让动态 3D 烛火永远精准点在蜡烛尖上。
4. 自动切分 3:2 展开内页为左右对称双页、提取全新封面的协调色盘，并将图片压缩转成可直接塞进单文件 HTML 的高清 DataURI。
"""

import argparse
import base64
import colorsys
import io
import json
import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageFilter, ImageOps


def sample_corner_white_threshold(img_rgb: Image.Image) -> int:
    """
    采样图片四个角落像素的最低通道亮度，自适应计算安全的去白底阈值。
    既保证微暖纸白底也能抠干净，又防止阈值过低伤及主体浅色衣物。
    """
    w, h = img_rgb.size
    pixels = img_rgb.load()
    sample_points = [
        (0, 0), (min(3, w - 1), min(3, h - 1)),
        (w - 1, 0), (max(0, w - 4), min(3, h - 1)),
        (0, h - 1), (min(3, w - 1), max(0, h - 4)),
        (w - 1, h - 1), (max(0, w - 4), max(0, h - 4)),
    ]
    corner_mins = [min(pixels[x, y]) for x, y in sample_points]
    avg_corner = sum(corner_mins) / len(corner_mins)
    if avg_corner >= 246:
        return 238
    if avg_corner >= 232:
        return int(avg_corner - 10)
    return 228


def flood_fill_white_background(
    img_rgb: Image.Image,
    threshold: Optional[int] = None,
    allow_inner_hole: bool = False,
) -> Image.Image:
    """
    从图像四条外边框连通向内执行洪水泛洪（BFS），找出全部外部纯白背景像素。
    返回 L 模式前景掩码（255 = 主体前景，0 = 外部纯白底）。
    """
    w, h = img_rgb.size
    pixels = img_rgb.load()
    thresh = threshold if threshold is not None else sample_corner_white_threshold(img_rgb)

    visited = bytearray(w * h)
    is_bg = bytearray(w * h)
    q: deque[Tuple[int, int]] = deque()

    def is_bg_pixel(x: int, y: int) -> bool:
        r, g, b = pixels[x, y]
        # 通道接近纯白或极大值且色彩饱和度极低，防止误杀浅亮高饱和点缀
        min_c = min(r, g, b)
        max_c = max(r, g, b)
        return min_c >= thresh and (max_c - min_c) <= 18

    for x in range(w):
        for y in (0, h - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_pixel(x, y):
                visited[idx] = 1
                is_bg[idx] = 1
                q.append((x, y))

    for y in range(h):
        for x in (0, w - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_pixel(x, y):
                visited[idx] = 1
                is_bg[idx] = 1
                q.append((x, y))

    # 如果是拱门立牌，底部正中央拱洞内也允许做透明镂空泛洪
    if allow_inner_hole:
        for ratio_y in (0.68, 0.78, 0.88):
            cx, cy = w // 2, min(h - 1, int(h * ratio_y))
            idx = cy * w + cx
            if not visited[idx] and is_bg_pixel(cx, cy):
                visited[idx] = 1
                is_bg[idx] = 1
                q.append((cx, cy))

    while q:
        cx, cy = q.popleft()
        if cx > 0:
            nidx = cy * w + (cx - 1)
            if not visited[nidx]:
                visited[nidx] = 1
                if is_bg_pixel(cx - 1, cy):
                    is_bg[nidx] = 1
                    q.append((cx - 1, cy))
        if cx + 1 < w:
            nidx = cy * w + (cx + 1)
            if not visited[nidx]:
                visited[nidx] = 1
                if is_bg_pixel(cx + 1, cy):
                    is_bg[nidx] = 1
                    q.append((cx + 1, cy))
        if cy > 0:
            nidx = (cy - 1) * w + cx
            if not visited[nidx]:
                visited[nidx] = 1
                if is_bg_pixel(cx, cy - 1):
                    is_bg[nidx] = 1
                    q.append((cx, cy - 1))
        if cy + 1 < h:
            nidx = (cy + 1) * w + cx
            if not visited[nidx]:
                visited[nidx] = 1
                if is_bg_pixel(cx, cy + 1):
                    is_bg[nidx] = 1
                    q.append((cx, cy + 1))

    fg_bytes = bytearray(255 if b == 0 else 0 for b in is_bg)
    return Image.frombytes("L", (w, h), bytes(fg_bytes))


def remove_small_components(
    fg_mask: Image.Image,
    min_ratio: float = 0.006,
    min_pixels: int = 160,
) -> Image.Image:
    """
    自动清除前景掩码中远离主体的孤立碎杂点/水印残点（连通域面积过滤）。
    根治不同 AI Agent 生成白底图时画布角落偶发微小杂点导致立牌包围盒被撑大、上台穿模的问题。
    """
    w, h = fg_mask.size
    raw = fg_mask.tobytes()
    visited = bytearray(w * h)
    components: List[List[int]] = []

    for idx in range(w * h):
        if raw[idx] == 0 or visited[idx]:
            continue
        comp: List[int] = []
        q = deque([idx])
        visited[idx] = 1
        while q:
            cur = q.popleft()
            comp.append(cur)
            cx = cur % w
            cy = cur // w
            if cx > 0:
                n = cur - 1
                if raw[n] and not visited[n]:
                    visited[n] = 1
                    q.append(n)
            if cx + 1 < w:
                n = cur + 1
                if raw[n] and not visited[n]:
                    visited[n] = 1
                    q.append(n)
            if cy > 0:
                n = cur - w
                if raw[n] and not visited[n]:
                    visited[n] = 1
                    q.append(n)
            if cy + 1 < h:
                n = cur + w
                if raw[n] and not visited[n]:
                    visited[n] = 1
                    q.append(n)
        components.append(comp)

    if not components:
        return fg_mask

    max_area = max(len(c) for c in components)
    threshold = max(min_pixels, int(max_area * min_ratio))
    cleaned = bytearray(w * h)
    for comp in components:
        if len(comp) >= threshold:
            for p in comp:
                cleaned[p] = 255
    return Image.frombytes("L", (w, h), bytes(cleaned))


def create_die_cut_standee(
    src_path: str,
    out_path: Optional[str] = None,
    border_px: int = 12,
    target_max_size: int = 920,
    allow_inner_hole: bool = False,
) -> Image.Image:
    """
    把白底插画裁切成带圆润 300g 米白厚卡纸刀模留白边（#FAF6EC）的透明 RGBA 立牌。
    若输入本身已是四角透明的成品 PNG，则保留原有透明通道并紧凑裁剪边缘。
    """
    raw = Image.open(src_path)
    if max(raw.size) > target_max_size:
        raw.thumbnail((target_max_size, target_max_size), Image.Resampling.LANCZOS)

    # 判断原图是否本身已经带透明背景（例如手工预设的成品 PNG）
    if raw.mode == "RGBA":
        alpha_extrema = raw.getchannel("A").getextrema()
        w0, h0 = raw.size
        corners_alpha = [
            raw.getpixel((0, 0))[3],
            raw.getpixel((w0 - 1, 0))[3],
            raw.getpixel((0, h0 - 1))[3],
            raw.getpixel((w0 - 1, h0 - 1))[3],
        ]
        if alpha_extrema[0] < 20 and max(corners_alpha) < 30:
            bbox = raw.getbbox()
            result = raw.crop(bbox) if bbox else raw
            if out_path:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                result.save(out_path, "PNG", optimize=True)
            return result

    img = raw.convert("RGB")
    fg_mask = flood_fill_white_background(img, allow_inner_hole=allow_inner_hole)
    # 轻微收缩 1px 消除扫描抗锯齿白丝，并自动清除画布角落零散孤立碎杂点（根治立牌包围盒撑大穿模）
    fg_clean = remove_small_components(fg_mask.filter(ImageFilter.MinFilter(3)))

    # 在四周预留安全内边距避免白边被画布四边切平
    pad_work = border_px * 2 + 12
    w_orig, h_orig = img.size
    canvas_w = w_orig + pad_work * 2
    canvas_h = h_orig + pad_work * 2

    img_padded = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    img_padded.paste(img, (pad_work, pad_work))

    mask_padded = Image.new("L", (canvas_w, canvas_h), 0)
    mask_padded.paste(fg_clean, (pad_work, pad_work))

    # 多次圆润膨胀生成真实刀模米白卡纸轮廓
    die_mask = mask_padded
    steps = max(1, border_px // 2)
    for _ in range(steps):
        die_mask = die_mask.filter(ImageFilter.MaxFilter(5))
    die_smooth = die_mask.filter(ImageFilter.GaussianBlur(radius=3.0))
    die_alpha = die_smooth.point(lambda p: 0 if p < 95 else min(255, int((p - 95) * 3.2)))

    # 合成 #FAF6EC 温暖米白水彩卡纸底板 + 外圈细微刀模压痕描边
    paper_base = Image.new("RGB", (canvas_w, canvas_h), (250, 246, 236))
    inner_mask = die_alpha.filter(ImageFilter.MinFilter(3))
    edge_ring = ImageChops.subtract(die_alpha, inner_mask)
    edge_tint = Image.new("RGB", (canvas_w, canvas_h), (216, 206, 188))
    paper_base = Image.composite(edge_tint, paper_base, edge_ring.point(lambda p: int(p * 0.52)))

    fg_feather = mask_padded.filter(ImageFilter.GaussianBlur(radius=0.85))
    combined_rgb = Image.composite(img_padded, paper_base, fg_feather)

    result = combined_rgb.convert("RGBA")
    result.putalpha(die_alpha)

    bbox = result.getbbox()
    if bbox:
        crop_pad = 6
        result = result.crop((
            max(0, bbox[0] - crop_pad),
            max(0, bbox[1] - crop_pad),
            min(canvas_w, bbox[2] + crop_pad),
            min(canvas_h, bbox[3] + crop_pad),
        ))

    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        result.save(out_path, "PNG", optimize=True)
    return result


def detect_candle_wick_position(standee_rgba: Image.Image) -> Dict[str, float]:
    """
    自动扫描裁切后的蛋糕立体图像顶部区域，识别细蜡烛柱的最顶端中心位置，
    返回供动态火焰使用的百分比坐标 {leftPct, topPct}。
    若图像结构不明确则安全回退默认推荐位置。
    """
    w, h = standee_rgba.size
    px = standee_rgba.load()

    scan_y_start = int(h * 0.02)
    scan_y_end = int(h * 0.24)
    cand_points = []

    for y in range(scan_y_start, scan_y_end):
        row_xs = []
        for x in range(int(w * 0.22), int(w * 0.78)):
            r, g, b, a = px[x, y]
            # 跳过半透明边和米白刀模留白卡纸边，寻找真正蜡烛笔触
            if a > 200 and (min(r, g, b) < 232 or (max(r, g, b) - min(r, g, b)) > 16):
                row_xs.append(x)
        # 细蜡烛通常宽度在 2px ~ 16% 画幅之间
        if 2 <= len(row_xs) <= int(w * 0.16):
            cand_points.append((y, sum(row_xs) / len(row_xs)))
            if len(cand_points) >= 8:
                break

    if not cand_points:
        return {"leftPct": 44.6, "topPct": 7.5}

    wick_y = cand_points[0][0]
    avg_x = sum(p[1] for p in cand_points) / len(cand_points)
    left_pct = round(max(28.0, min(72.0, (avg_x / w) * 100.0)), 2)
    top_pct = round(max(3.5, min(20.0, (wick_y / h) * 100.0)), 2)
    return {"leftPct": left_pct, "topPct": top_pct}


def detect_tree_light_anchors(standee_rgba: Image.Image) -> Dict[str, Any]:
    """
    自动扫描裁切后的立体圣诞树轮廓，定位树顶主星位置，并在树冠真实绿叶内部错落分布 13 颗暖光星星灯坐标。
    确保无论哪家 AI 生成什么高矮胖瘦的圣诞树，所有闪烁星星灯都稳稳挂在树枝上绝不飘到树外。
    """
    w, h = standee_rgba.size
    px = standee_rgba.load()

    def scan_row_span(y_idx: int) -> Optional[Tuple[int, int]]:
        xs = []
        for x in range(w):
            r, g, b, a = px[x, y_idx]
            if a > 210 and (min(r, g, b) < 235 or (max(r, g, b) - min(r, g, b)) > 16):
                xs.append(x)
        if len(xs) < 6:
            return None
        return xs[0], xs[-1]

    # 1. 寻找树顶主星锚点
    top_star = {"leftPct": 50.0, "topPct": 8.5}
    for y in range(int(h * 0.02), int(h * 0.24)):
        span = scan_row_span(y)
        if span:
            cx = (span[0] + span[1]) / 2.0
            top_star = {
                "leftPct": round(max(34.0, min(66.0, (cx / w) * 100.0)), 2),
                "topPct": round(max(4.5, min(20.0, ((y + h * 0.028) / h) * 100.0)), 2),
            }
            break

    # 2. 按 5 个高度层在树冠安全内缩区间布置错落星灯
    row_specs = [
        (0.24, 2, (0.34, 0.66)),
        (0.36, 2, (0.24, 0.74)),
        (0.49, 3, (0.20, 0.52, 0.80)),
        (0.61, 3, (0.18, 0.48, 0.82)),
        (0.73, 3, (0.22, 0.54, 0.79)),
    ]
    lights: List[Dict[str, Any]] = []
    phase_idx = 0
    for y_ratio, _cnt, frac_positions in row_specs:
        y_idx = min(h - 1, max(0, int(h * y_ratio)))
        span = scan_row_span(y_idx)
        if not span:
            continue
        x0, x1 = span
        row_w = x1 - x0
        if row_w < 16:
            continue
        for pos_idx, frac in enumerate(frac_positions):
            lx = x0 + row_w * frac
            # 上下微幅自然错落，像手工绕上的暖光灯串
            ly = y_idx + ((-1) ** (phase_idx + pos_idx)) * h * 0.016
            lights.append({
                "leftPct": round(max(12.0, min(88.0, (lx / w) * 100.0)), 2),
                "topPct": round(max(14.0, min(82.0, (ly / h) * 100.0)), 2),
                "size": 10 if (phase_idx % 3 == 0) else 8,
                "delay": round((phase_idx * 0.37) % 2.2, 2),
                "duration": round(1.55 + (phase_idx % 4) * 0.32, 2),
                "warm": (phase_idx % 2 == 0),
            })
            phase_idx += 1

    if len(lights) < 6:
        lights = [
            {"leftPct": 46.0, "topPct": 25.0, "size": 9, "delay": 0.1, "duration": 1.7, "warm": True},
            {"leftPct": 55.0, "topPct": 31.0, "size": 8, "delay": 0.5, "duration": 2.0, "warm": False},
            {"leftPct": 41.0, "topPct": 40.0, "size": 10, "delay": 0.9, "duration": 1.6, "warm": True},
            {"leftPct": 58.0, "topPct": 44.0, "size": 8, "delay": 1.2, "duration": 2.2, "warm": False},
            {"leftPct": 36.0, "topPct": 55.0, "size": 9, "delay": 0.3, "duration": 1.9, "warm": True},
            {"leftPct": 50.0, "topPct": 53.0, "size": 10, "delay": 0.8, "duration": 1.7, "warm": False},
            {"leftPct": 64.0, "topPct": 57.0, "size": 8, "delay": 1.4, "duration": 2.1, "warm": True},
            {"leftPct": 33.0, "topPct": 69.0, "size": 9, "delay": 0.6, "duration": 1.8, "warm": False},
            {"leftPct": 49.0, "topPct": 67.0, "size": 10, "delay": 1.1, "duration": 2.0, "warm": True},
            {"leftPct": 66.0, "topPct": 70.0, "size": 8, "delay": 0.2, "duration": 1.6, "warm": False},
        ]

    return {"topStar": top_star, "lights": lights}


def hsl_to_hex(h_deg: float, s_pct: float, l_pct: float) -> str:
    """将色相(0-360)、饱和度(0-100)、明度(0-100)转为 #rrggbb 格式 HEX 色值。"""
    s = max(0.0, min(1.0, s_pct / 100.0))
    l = max(0.0, min(1.0, l_pct / 100.0))
    r, g, b = colorsys.hls_to_rgb((h_deg % 360.0) / 360.0, l, s)
    return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"


def extract_palette_from_cover(cover_img: Image.Image) -> Dict[str, str]:
    """
    自动从新绘贺卡封面中分析色彩气氛，衍生出最和谐的桌面对衬色、强调色与火漆圆章配色。
    """
    thumb = cover_img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    pixels = thumb.getdata()

    buckets = [{"count": 0, "r": 0, "g": 0, "b": 0} for _ in range(12)]
    total_r = total_g = total_b = count_all = 0

    for r, g, b in pixels:
        total_r += r
        total_g += g
        total_b += b
        count_all += 1
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        if s > 0.18 and 0.18 < l < 0.84:
            idx = int((h * 360.0) // 30) % 12
            buckets[idx]["count"] += 1
            buckets[idx]["r"] += r
            buckets[idx]["g"] += g
            buckets[idx]["b"] += b

    buckets.sort(key=lambda item: item["count"], reverse=True)
    primary = buckets[0] if buckets[0]["count"] > 0 else {"count": 1, "r": 79, "g": 115, "b": 72}
    secondary = buckets[1] if buckets[1]["count"] > 4 else {"count": 1, "r": 181, "g": 73, "b": 107}

    pr = primary["r"] / primary["count"]
    pg = primary["g"] / primary["count"]
    pb = primary["b"] / primary["count"]
    ph, pl, ps = colorsys.rgb_to_hls(pr / 255.0, pg / 255.0, pb / 255.0)
    ph_deg = ph * 360.0

    sr = secondary["r"] / secondary["count"]
    sg = secondary["g"] / secondary["count"]
    sb = secondary["b"] / secondary["count"]
    sh, sl, ss = colorsys.rgb_to_hls(sr / 255.0, sg / 255.0, sb / 255.0)
    sh_deg = sh * 360.0

    avg_h, _, _ = colorsys.rgb_to_hls(
        (total_r / count_all) / 255.0,
        (total_g / count_all) / 255.0,
        (total_b / count_all) / 255.0,
    )
    avg_h_deg = avg_h * 360.0

    # 让桌面色调呈温和低饱和木质/哑光纸桌感，避免抢走卡片风头
    is_cool = 165.0 <= ph_deg <= 265.0
    table_hue = avg_h_deg if is_cool else min(42.0, max(28.0, avg_h_deg))
    table_inner = hsl_to_hex(table_hue, 22 if is_cool else 34, 86)
    table_outer = hsl_to_hex(table_hue, 18 if is_cool else 28, 74)

    primary_accent = hsl_to_hex(ph_deg, min(58.0, max(30.0, ps * 100.0)), min(46.0, max(32.0, pl * 100.0)))
    secondary_accent = hsl_to_hex(sh_deg, min(65.0, max(34.0, ss * 100.0)), min(58.0, max(38.0, sl * 100.0)))
    wax_seal = hsl_to_hex(sh_deg, 62.0, 44.0) if (sh_deg < 35.0 or sh_deg > 320.0) else "#b9382e"

    return {
        "styleName": "定制同系艺术风格",
        "tableInner": table_inner,
        "tableOuter": table_outer,
        "paperCream": "#faf6ec",
        "primaryAccent": primary_accent,
        "secondaryAccent": secondary_accent,
        "waxSealColor": wax_seal,
        "filterCss": "none",
    }


def align_arch_feet(img: Image.Image) -> Image.Image:
    """Trim both feet along a shared horizontal cut on a two-foot vertical arch."""
    alpha = img.getchannel("A")
    solid = alpha.point(lambda value: 255 if value >= 192 else 0)
    bounds = solid.getbbox()
    if not bounds:
        return img
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    feet = []
    for start, stop in ((0.07, 0.31), (0.69, 0.93)):
        columns = range(left + int(start * width), left + int(stop * width))
        ends = sorted(
            box[3] for x in columns
            if (box := solid.crop((x, top, x + 1, bottom)).getbbox())
        )
        if not ends:
            return img
        feet.append(top + ends[int(0.8 * (len(ends) - 1))])
    shorter_foot = min(feet)
    if bottom - shorter_foot > height * 0.07:
        return img
    cut = shorter_foot - max(1, height // 300)
    foot_span = solid.crop((0, cut - 1, img.width, cut)).getbbox()
    # Crop transparent side margins at the two outer footing edges.
    if foot_span and foot_span[0] - left <= width * 0.02 and right - foot_span[2] <= width * 0.02:
        return img.crop((foot_span[0], 0, foot_span[2], cut))
    return img.crop((0, 0, img.width, cut))


def fit_cover_surface(cover_path: str, size: Tuple[int, int] = (750, 1000)) -> Image.Image:
    """将重绘好的封面图等比居中裁切贴合为标准 3:4 竖版卡片比例。"""
    img = Image.open(cover_path).convert("RGB")
    return ImageOps.fit(img, size, Image.Resampling.LANCZOS)


def split_inside_spread(
    inside_path: str,
    size: Tuple[int, int] = (1400, 934),
    *,
    vertical: bool = False,
) -> Tuple[Image.Image, Image.Image]:
    """将展开底图沿折线平分，按左至右或上至下返回两页。"""
    img = Image.open(inside_path).convert("RGB")
    fitted = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
    if vertical:
        half_h = size[1] // 2
        return fitted.crop((0, 0, size[0], half_h)), fitted.crop((0, half_h, size[0], size[1]))
    half_w = size[0] // 2
    left = fitted.crop((0, 0, half_w, size[1]))
    right = fitted.crop((half_w, 0, size[0], size[1]))
    return left, right


def image_to_data_uri(img: Image.Image, fmt: str = "WEBP", quality: int = 86, max_dim: Optional[int] = None) -> str:
    """
    将 Pillow Image 对象压缩编码为自包含的 base64 DataURI，支持透明通道与渐进回退。
    """
    work = img.copy()
    if max_dim and max(work.size) > max_dim:
        work.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    fmt_upper = fmt.upper()
    try:
        if fmt_upper == "WEBP":
            work.save(buf, format="WEBP", quality=quality, method=4)
            mime = "image/webp"
        elif fmt_upper == "JPEG":
            if work.mode != "RGB":
                work = work.convert("RGB")
            work.save(buf, format="JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        else:
            work.save(buf, format="PNG", optimize=True)
            mime = "image/png"
    except Exception:
        # 少数老旧平台缺少 WebP 编码库时安全回退到 PNG 或 JPEG
        buf = io.BytesIO()
        if "A" in work.getbands():
            work.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        else:
            work.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def compute_image_similarity(path_a: str, path_b: str) -> float:
    """
    计算两张图片在 24x24 低分辨率下的视觉近似度（0.0 ~ 1.0）。
    用于在打包阶段自动检测并拦截“未做重绘、直接把风格参考原图硬贴当封面”的偷懒行为。
    """
    if not os.path.isfile(path_a) or not os.path.isfile(path_b):
        return 0.0
    if os.path.abspath(path_a) == os.path.abspath(path_b):
        return 1.0
    a = ImageOps.fit(Image.open(path_a).convert("RGB"), (24, 24), Image.Resampling.BILINEAR)
    b = ImageOps.fit(Image.open(path_b).convert("RGB"), (24, 24), Image.Resampling.BILINEAR)
    pa = list(a.getdata())
    pb = list(b.getdata())
    diff_sum = sum(abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2]) for c1, c2 in zip(pa, pb))
    max_diff = len(pa) * 3 * 255
    return round(1.0 - (diff_sum / max_diff), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="独立纸艺刀模切边与图片预处理命令行工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cut = sub.add_parser("diecut", help="为单张白底插画抠图并加上米白厚卡纸刀模边缘")
    p_cut.add_argument("--input", required=True, help="输入白底图片路径")
    p_cut.add_argument("--output", required=True, help="输出透明 PNG 路径")
    p_cut.add_argument("--border", type=int, default=12, help="卡纸白边宽度像素（默认 12）")
    p_cut.add_argument("--inner-hole", action="store_true", help="同时挖空拱门底部中央空白洞")
    p_cut.add_argument("--detect-wick", action="store_true", help="顺便探测蛋糕顶部蜡烛芯坐标")
    p_cut.add_argument("--detect-tree-lights", action="store_true", help="顺便探测圣诞树顶星与树冠星灯坐标")

    p_pal = sub.add_parser("palette", help="分析封面图并返回协调主题色盘 JSON")
    p_pal.add_argument("--cover", required=True, help="封面图片路径")

    args = parser.parse_args()
    if args.cmd == "diecut":
        standee = create_die_cut_standee(
            args.input,
            args.output,
            border_px=args.border,
            allow_inner_hole=args.inner_hole,
        )
        info = {"ok": True, "output": args.output, "size": standee.size}
        if args.detect_wick:
            info["cakeWickPos"] = detect_candle_wick_position(standee)
        if args.detect_tree_lights:
            info["treeLights"] = detect_tree_light_anchors(standee)
        print(json.dumps(info, ensure_ascii=False))
    elif args.cmd == "palette":
        img = Image.open(args.cover).convert("RGB")
        print(json.dumps(extract_palette_from_cover(img), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
