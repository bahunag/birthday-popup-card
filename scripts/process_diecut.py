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
import sys
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
    min_ratio: float = 0.0025,
    min_pixels: int = 24,
) -> Image.Image:
    """
    结合连通域面积与到主体核心包围盒的距离，清理远离主体的孤立碎杂点/角落圆点，
    同时保护紧贴主体的精细结构（如蛋糕顶部细蜡烛芯、树顶小星等）不被误删。
    """
    w, h = fg_mask.size
    raw = fg_mask.tobytes()
    visited = bytearray(w * h)
    components: List[Tuple[List[int], Tuple[int, int, int, int]]] = []

    for idx in range(w * h):
        if raw[idx] == 0 or visited[idx]:
            continue
        comp: List[int] = []
        q = deque([idx])
        visited[idx] = 1
        min_x = w
        min_y = h
        max_x = -1
        max_y = -1
        while q:
            cur = q.popleft()
            comp.append(cur)
            cx = cur % w
            cy = cur // w
            if cx < min_x:
                min_x = cx
            if cx > max_x:
                max_x = cx
            if cy < min_y:
                min_y = cy
            if cy > max_y:
                max_y = cy
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
        components.append((comp, (min_x, min_y, max_x, max_y)))

    if not components:
        return fg_mask

    max_area = max(len(c) for c, _ in components)
    core_thresh = max(min_pixels, int(max_area * 0.02))
    mx0, my0, mx1, my1 = w, h, -1, -1
    for comp, (x0, y0, x1, y1) in components:
        if len(comp) >= core_thresh or len(comp) == max_area:
            mx0 = min(mx0, x0)
            my0 = min(my0, y0)
            mx1 = max(mx1, x1)
            my1 = max(my1, y1)

    near_dist = max(14, int(min(w, h) * 0.04))
    far_dist = max(20, int(min(w, h) * 0.06))
    far_area_thresh = max(320, int(max_area * 0.045))
    mid_thresh = max(min_pixels, int(max_area * min_ratio))

    cleaned = bytearray(w * h)
    for comp, (x0, y0, x1, y1) in components:
        area = len(comp)
        dx = max(mx0 - x1, x0 - mx1, 0)
        dy = max(my0 - y1, y0 - my1, 0)
        dist = max(dx, dy)

        if area >= core_thresh or area == max_area:
            keep = True
        elif dist <= near_dist:
            # 紧贴主体的细小关键细节（如独立细蜡烛芯、小花瓣）保留
            keep = area >= 5
        elif dist > far_dist:
            # 远离主体的孤立小噪点/角落圆点坚决清除
            keep = area >= far_area_thresh
        else:
            keep = area >= mid_thresh

        if keep:
            for p in comp:
                cleaned[p] = 255
    return Image.frombytes("L", (w, h), bytes(cleaned))


def validate_standee_visibility(
    standee_rgba: Image.Image,
    min_pixels: int = 400,
    min_ratio: float = 0.012,
) -> Tuple[bool, float]:
    """
    检查裁切后的立牌是否包含真实可见的主体内容（拦截纯白空图、全透明图或仅剩极少噪点的无效素材）。
    """
    w, h = standee_rgba.size
    if w <= 0 or h <= 0:
        return False, 0.0
    total = w * h
    px = standee_rgba.convert("RGBA").getdata()
    opaque_count = 0
    drawn_count = 0
    for r, g, b, a in px:
        if a > 200:
            opaque_count += 1
            if min(r, g, b) < 238 or (max(r, g, b) - min(r, g, b)) > 12:
                drawn_count += 1
    ratio = opaque_count / float(total)
    min_drawn = max(60, min(min_pixels // 2, int(total * 0.004)))
    is_valid = opaque_count >= min(min_pixels, max(80, total // 12)) and drawn_count >= min_drawn and ratio >= min_ratio
    return is_valid, round(ratio, 4)


def create_die_cut_standee(
    src_path: str,
    out_path: Optional[str] = None,
    border_px: int = 12,
    target_max_size: int = 920,
    allow_inner_hole: bool = False,
) -> Image.Image:
    """
    把白底插画裁切成带圆润 300g 米白厚卡纸刀模留白边（#FAF6EC）的透明 RGBA 立牌。
    若输入本身已是四角透明的成品 PNG，则先清理远离主体的角落碎杂点再紧凑裁剪边缘。
    """
    raw = Image.open(src_path)
    if max(raw.size) > target_max_size:
        raw.thumbnail((target_max_size, target_max_size), Image.Resampling.LANCZOS)

    # 判断原图是否本身已经带透明背景（例如手工预设的成品 PNG）
    if raw.mode == "RGBA":
        alpha_ch = raw.getchannel("A")
        alpha_extrema = alpha_ch.getextrema()
        w0, h0 = raw.size
        corners_alpha = [
            raw.getpixel((0, 0))[3],
            raw.getpixel((w0 - 1, 0))[3],
            raw.getpixel((0, h0 - 1))[3],
            raw.getpixel((w0 - 1, h0 - 1))[3],
        ]
        if alpha_extrema[0] < 20 and max(corners_alpha) < 30:
            alpha_bin = alpha_ch.point(lambda p: 255 if p > 24 else 0)
            clean_bin = remove_small_components(alpha_bin)
            clean_alpha = ImageChops.darker(alpha_ch, clean_bin)
            cleaned_rgba = raw.copy()
            cleaned_rgba.putalpha(clean_alpha)
            bbox = cleaned_rgba.getbbox()
            result = cleaned_rgba.crop(bbox) if bbox else cleaned_rgba
            if out_path:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                result.save(out_path, "PNG", optimize=True)
            return result

    img = raw.convert("RGB")
    fg_mask = flood_fill_white_background(img, allow_inner_hole=allow_inner_hole)
    # 先保留完整细小特征并按距离清理角落碎杂点，绝不先 MinFilter 吞掉 2~3px 细蜡烛芯/枝梢
    fg_clean = remove_small_components(fg_mask)

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

    # 使用极微柔边（0.35px）保持 2~3px 精细深色线条完整锐利、不被米白卡纸冲淡
    fg_feather = mask_padded.filter(ImageFilter.GaussianBlur(radius=0.35))
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


def _erode_binary_mask(mask: Image.Image, radius_px: int) -> Image.Image:
    """对二值 L 掩码向内平滑腐蚀约 radius_px 像素，去除外围米白卡纸白边并留出树冠内芯安全区。"""
    eroded = mask
    steps = max(1, radius_px // 2)
    for _ in range(steps):
        eroded = eroded.filter(ImageFilter.MinFilter(5))
    return eroded


def detect_tree_light_anchors(standee_rgba: Image.Image) -> Dict[str, Any]:
    """
    自动扫描裁切后的立体圣诞树实体轮廓（完全基于 Alpha 实体内缩掩码，兼容深绿、浅绿、偏黄及白雪圣诞树与分叉树）：
    1. 精确将树顶主星钉在树尖真实实体中心（绝不偏离树尖）；
    2. 按高度层扫描真实连续树冠实心区间并跳过分叉空隙，逐点校验 5x5 像素均处于树冠实心内芯，
       树冠较窄或分叉严重时自动减少灯数，确保 100% 不悬空飘到树外。
    """
    w, h = standee_rgba.size
    alpha_ch = standee_rgba.convert("RGBA").getchannel("A")
    solid_mask = alpha_ch.point(lambda p: 255 if p > 215 else 0)

    # 先轻度腐蚀去除外围米白刀模边（保留树尖实体），定位树顶星
    top_erode_px = max(4, min(10, int(min(w, h) * 0.02)))
    top_mask = _erode_binary_mask(solid_mask, top_erode_px)
    if not top_mask.getbbox():
        top_mask = solid_mask
    top_px = top_mask.load()

    def scan_mask_segments(px_map: Any, y_idx: int) -> List[Tuple[int, int]]:
        segments: List[Tuple[int, int]] = []
        in_seg = False
        seg_start = 0
        for x in range(w):
            if px_map[x, y_idx] > 128:
                if not in_seg:
                    in_seg = True
                    seg_start = x
            elif in_seg:
                in_seg = False
                segments.append((seg_start, x - 1))
        if in_seg:
            segments.append((seg_start, w - 1))
        return segments

    # 1. 寻找真实树尖位置（取最先出现实心树尖的连续数行做水平均值，竖向直接锚定树尖顶部）
    top_star = {"leftPct": 50.0, "topPct": 8.5}
    peak_rows: List[Tuple[int, float]] = []
    for y in range(int(h * 0.01), int(h * 0.28)):
        segs = scan_mask_segments(top_px, y)
        if not segs:
            continue
        longest = max(segs, key=lambda s: s[1] - s[0])
        if longest[1] - longest[0] >= 3:
            peak_rows.append((y, (longest[0] + longest[1]) / 2.0))
            if len(peak_rows) >= 5:
                break
    if peak_rows:
        peak_y = peak_rows[0][0]
        peak_cx = sum(item[1] for item in peak_rows) / len(peak_rows)
        # 确保树尖本身处于实心区域内（若第 0 行特别窄则微向下 1.2% 确保金星稳落树顶）
        anchor_y = min(int(h * 0.26), peak_y + max(2, int(h * 0.012)))
        top_star = {
            "leftPct": round(max(20.0, min(80.0, (peak_cx / w) * 100.0)), 2),
            "topPct": round(max(2.5, min(28.0, (anchor_y / h) * 100.0)), 2),
        }

    # 2. 向内腐蚀得到完全避开卡纸边与最外缘锯齿的树冠安全实心内芯掩码
    crown_erode_px = max(12, min(22, int(min(w, h) * 0.036)))
    core_mask = _erode_binary_mask(solid_mask, crown_erode_px)
    if not core_mask.getbbox():
        core_mask = _erode_binary_mask(solid_mask, max(6, top_erode_px))
    core_px = core_mask.load()

    def is_point_inside_crown(cx_f: float, cy_f: float) -> bool:
        ix = int(round(cx_f))
        iy = int(round(cy_f))
        if ix < 2 or ix >= w - 2 or iy < 2 or iy >= h - 2:
            return False
        hits = 0
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                if core_px[ix + dx, iy + dy] > 128:
                    hits += 1
        return hits >= 22

    # 在树顶下方至树冠底缘之间均匀取 5 个高度层（避开底部木盆/树干根部）
    crown_top_y = (top_star["topPct"] / 100.0) * h
    crown_bot_y = h * 0.74
    layer_ratios = [0.18, 0.36, 0.54, 0.72, 0.90]
    layer_target_counts = [2, 2, 3, 3, 3]

    lights: List[Dict[str, Any]] = []
    min_dist_sq = (max(12.0, min(w, h) * 0.075)) ** 2
    phase_idx = 0

    for l_ratio, target_cnt in zip(layer_ratios, layer_target_counts):
        y_base = int(round(crown_top_y + (crown_bot_y - crown_top_y) * l_ratio))
        if y_base <= 4 or y_base >= h - 4:
            continue
        segs = [s for s in scan_mask_segments(core_px, y_base) if (s[1] - s[0]) >= max(8, int(w * 0.035))]
        if not segs:
            continue

        total_seg_w = sum((s[1] - s[0]) for s in segs)
        # 按连续实心枝干宽度比例在每段中安全取点，绝不跨越分叉中间空隙
        for seg_idx, (sx0, sx1) in enumerate(segs):
            seg_w = sx1 - sx0
            seg_quota = max(1, round(target_cnt * (seg_w / max(1, total_seg_w))))
            if seg_idx == 0 and len(segs) >= 2:
                seg_quota = max(1, target_cnt // len(segs))
            pad = min(seg_w * 0.22, max(4.0, w * 0.02))
            usable_w = max(1.0, seg_w - 2 * pad)
            for k in range(seg_quota):
                frac = 0.5 if seg_quota == 1 else (0.15 + 0.70 * (k / (seg_quota - 1)))
                cand_x = sx0 + pad + usable_w * frac
                jitter_y = ((-1) ** (phase_idx + k)) * min(6.0, h * 0.012)
                cand_y = min(crown_bot_y, max(crown_top_y + 8, y_base + jitter_y))

                # 优先取微调后的实心点；不行则退回严格处于该段中线的基准 y_base 点
                chosen_pt: Optional[Tuple[float, float]] = None
                for test_y in (cand_y, float(y_base), float(y_base - 4), float(y_base + 4)):
                    if is_point_inside_crown(cand_x, test_y):
                        chosen_pt = (cand_x, test_y)
                        break
                if chosen_pt is None:
                    mid_x = (sx0 + sx1) / 2.0
                    if is_point_inside_crown(mid_x, float(y_base)):
                        chosen_pt = (mid_x, float(y_base))
                if chosen_pt is None:
                    continue

                lx, ly = chosen_pt
                if any((lx - pt["_px"]) ** 2 + (ly - pt["_py"]) ** 2 < min_dist_sq for pt in lights):
                    continue

                lights.append({
                    "_px": lx,
                    "_py": ly,
                    "leftPct": round(max(4.0, min(96.0, (lx / w) * 100.0)), 2),
                    "topPct": round(max(5.0, min(88.0, (ly / h) * 100.0)), 2),
                    "size": 10 if (phase_idx % 3 == 0) else 8,
                    "delay": round((phase_idx * 0.37) % 2.2, 2),
                    "duration": round(1.55 + (phase_idx % 4) * 0.32, 2),
                    "warm": (phase_idx % 2 == 0),
                })
                phase_idx += 1

    # 清理内部临时像素坐标字段，保证输出字典完全纯净
    for pt in lights:
        pt.pop("_px", None)
        pt.pop("_py", None)

    return {"topStar": top_star, "lights": lights[:13]}


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
    """
    将重绘好的封面或内页图贴合为标准尺寸：
    - 常规相近比例（<= 1.45x）：等比居中满幅铺纸，避免留黑边；
    - 极端宽窄比例（> 1.45x，如超宽长条或超窄竖条）：自动切换为完整画面保边模式，
      以原图边缘采样的柔和纸底色自然补白，绝不裁掉画面两端重要信息或标题，并打印重画建议。
    """
    img = Image.open(cover_path).convert("RGB")
    sw, sh = img.size
    dw, dh = size
    if sw > 0 and sh > 0 and dw > 0 and dh > 0:
        src_r = sw / float(sh)
        dst_r = dw / float(dh)
        ratio_diff = max(src_r / dst_r, dst_r / src_r)
        if ratio_diff > 1.45:
            print(
                f"[提示] 图片 '{os.path.basename(cover_path)}' 原比例 ({sw}x{sh}) 与目标比例 ({dw}x{dh}) 差异较大（极端比例 {ratio_diff:.2f}x），"
                f"已自动切换为完整画面保边扩纸底模式以防裁切丢失边缘内容；如需满幅铺纸请按目标比例重新生成。",
                file=sys.stderr,
            )
            # 采样图片四边均值作为温和手绘纸底色，使保边留白自然融合
            px = img.load()
            samples = []
            step_x = max(1, sw // 24)
            step_y = max(1, sh // 24)
            for x in range(0, sw, step_x):
                samples.append(px[x, 0])
                samples.append(px[x, sh - 1])
            for y in range(0, sh, step_y):
                samples.append(px[0, y])
                samples.append(px[sw - 1, y])
            if samples:
                bg_color = tuple(int(sum(c[i] for c in samples) / len(samples)) for i in range(3))
            else:
                bg_color = (246, 241, 232)
            canvas = Image.new("RGB", size, bg_color)
            contained = ImageOps.contain(img, size, Image.Resampling.LANCZOS)
            offset_x = (dw - contained.width) // 2
            offset_y = (dh - contained.height) // 2
            canvas.paste(contained, (offset_x, offset_y))
            return canvas
        if ratio_diff > 1.08:
            print(
                f"[提示] 图片 '{os.path.basename(cover_path)}' 原比例 ({sw}x{sh}) 与目标比例 ({dw}x{dh}) 略有差异（{ratio_diff:.2f}x），"
                f"已等比居中贴合；若边缘装饰或题字靠近画幅最外缘，建议生成时留足安全边距。",
                file=sys.stderr,
            )
    return ImageOps.fit(img, size, Image.Resampling.LANCZOS)


def split_inside_spread(
    inside_path: str,
    size: Tuple[int, int] = (1400, 934),
    *,
    vertical: bool = False,
) -> Tuple[Image.Image, Image.Image]:
    """将展开底图沿折线平分，按左至右或上至下返回两页，并检查极端比例裁切风险。"""
    fitted = fit_cover_surface(inside_path, size=size)
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
