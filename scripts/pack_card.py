"""立体贺卡纯本地刀模抠图与正宗母版拼接器（V8.4 全闭环高保真版，仅依赖 Pillow，零联网零密钥）"""
import argparse, base64, colorsys, hashlib, io, json, math, os, random, re, sys, uuid
from collections import deque
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

RES = Path(__file__).resolve().parent.parent / "resources"
EXTS = (".png", ".jpg", ".jpeg", ".webp")


def find1(wd, *stems):
    if not wd or not wd.is_dir(): return None
    for s in stems:
        for e in EXTS:
            p = wd / f"{s}{e}"
            if p.is_file(): return str(p)
    return None


def flood_white(rgb, hole=False):
    w, h = rgb.size; px = rgb.load()
    pts = [(0,0),(min(3,w-1),min(3,h-1)),(w-1,0),(max(0,w-4),min(3,h-1)),(0,h-1),(min(3,w-1),max(0,h-4)),(w-1,h-1),(max(0,w-4),max(0,h-4))]
    ac = sum(min(px[x,y]) for x,y in pts) / 8.0
    th = 238 if ac >= 246 else (int(ac - 10) if ac >= 232 else 228)
    vis, bg, q = bytearray(w * h), bytearray(w * h), deque()
    def is_bg(x, y): r, g, b = px[x, y]; mn, mx = min(r, g, b), max(r, g, b); return mn >= th and mx - mn <= 18
    def seed(x, y):
        i = y * w + x
        if not vis[i] and is_bg(x, y): vis[i] = bg[i] = 1; q.append((x, y))
    for x in range(w): seed(x, 0); seed(x, h - 1)
    for y in range(h): seed(0, y); seed(w - 1, y)
    if hole:
        for ry in (.68, .78, .88): seed(w // 2, min(h - 1, int(h * ry)))
    while q:
        cx, cy = q.popleft()
        for nx, ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if not vis[ni]:
                    vis[ni] = 1
                    if is_bg(nx, ny): bg[ni] = 1; q.append((nx, ny))
    return Image.frombytes("L", (w, h), bytes(255 if b == 0 else 0 for b in bg))


def clean_dots(mask):
    """按距主体包围盒距离清除远处杂点，同时保护紧贴主体的 3px 细蜡烛芯。"""
    w, h = mask.size; raw = mask.tobytes(); vis = bytearray(w * h); comps = []
    for i in range(w * h):
        if not raw[i] or vis[i]: continue
        c, q = [], deque([i]); vis[i] = 1; x0, y0, x1, y1 = w, h, -1, -1
        while q:
            u = q.popleft(); c.append(u); x, y = u % w, u // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            if x > 0 and raw[u-1] and not vis[u-1]: vis[u-1] = 1; q.append(u-1)
            if x+1 < w and raw[u+1] and not vis[u+1]: vis[u+1] = 1; q.append(u+1)
            if y > 0 and raw[u-w] and not vis[u-w]: vis[u-w] = 1; q.append(u-w)
            if y+1 < h and raw[u+w] and not vis[u+w]: vis[u+w] = 1; q.append(u+w)
        comps.append((c, (x0, y0, x1, y1)))
    if not comps: return mask
    ma = max(len(c) for c, _ in comps); ct = max(24, int(ma * .02))
    mx0, my0, mx1, my1 = w, h, -1, -1
    for c, (x0, y0, x1, y1) in comps:
        if len(c) >= ct or len(c) == ma: mx0, my0, mx1, my1 = min(mx0, x0), min(my0, y0), max(mx1, x1), max(my1, y1)
    nd, fd, ft, mt = max(14, int(min(w, h) * .04)), max(20, int(min(w, h) * .06)), max(320, int(ma * .045)), max(24, int(ma * .0025))
    out = bytearray(w * h)
    for c, (x0, y0, x1, y1) in comps:
        a, d = len(c), max(mx0 - x1, x0 - mx1, my0 - y1, y0 - my1, 0)
        if a >= ct or a == ma or (a >= 5 if d <= nd else (a >= ft if d > fd else a >= mt)):
            for p in c: out[p] = 255
    return Image.frombytes("L", (w, h), bytes(out))


def check_vis(rgba):
    w, h = rgba.size; tot = w * h
    if tot <= 0: return False, 0.0
    op = dr = 0
    for r, g, b, a in rgba.convert("RGBA").getdata():
        if a > 200:
            op += 1
            if min(r, g, b) < 238 or max(r, g, b) - min(r, g, b) > 12: dr += 1
    rat = op / float(tot)
    return (op >= min(400, max(80, tot // 12)) and dr >= max(60, min(200, int(tot * .004))) and rat >= .012), round(rat, 4)


def standee(src, border=12, max_sz=860, hole=False):
    """识别透明 PNG 或白底图片，清除角落杂点并生成 300g 米白卡纸刀模边。"""
    raw = Image.open(src)
    if max(raw.size) > max_sz: raw.thumbnail((max_sz, max_sz), Image.Resampling.LANCZOS)
    if raw.mode in ("RGBA", "LA", "PA") or "transparency" in raw.info:
        rgba0 = raw.convert("RGBA"); ac = rgba0.getchannel("A"); w0, h0 = rgba0.size
        if ac.getextrema()[0] < 20:
            apx = ac.load(); st = max(1, min(w0, h0) // 64)
            bs = [apx[x, y] for x in range(0, w0, st) for y in (0, h0 - 1)] + [apx[x, y] for y in range(0, h0, st) for x in (0, w0 - 1)]
            btr = sum(1 for v in bs if v < 30) / float(max(1, len(bs)))
            ttr = sum(ac.histogram()[:30]) / float(max(1, w0 * h0))
            if btr >= .55 or (ttr >= .15 and btr >= .35):
                res = rgba0.copy(); res.putalpha(ImageChops.darker(ac, clean_dots(ac.point(lambda p: 255 if p > 24 else 0))))
                bb = res.getchannel("A").getbbox(); return res.crop(bb) if bb else res
        bgw = Image.new("RGBA", rgba0.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bgw, rgba0).convert("RGB")
    else:
        img = raw.convert("RGB")
    fg = clean_dots(flood_white(img, hole))
    pad = border * 2 + 12; cw, ch = img.width + pad * 2, img.height + pad * 2
    ip = Image.new("RGB", (cw, ch), (255, 255, 255)); ip.paste(img, (pad, pad))
    mp = Image.new("L", (cw, ch), 0); mp.paste(fg, (pad, pad))
    die = mp
    for _ in range(max(1, border // 2)): die = die.filter(ImageFilter.MaxFilter(5))
    da = die.filter(ImageFilter.GaussianBlur(3.0)).point(lambda p: 0 if p < 95 else min(255, int((p - 95) * 3.2)))
    pp = Image.new("RGB", (cw, ch), (250, 246, 236))
    ring = ImageChops.subtract(da, da.filter(ImageFilter.MinFilter(3)))
    pp = Image.composite(Image.new("RGB", (cw, ch), (216, 206, 188)), pp, ring.point(lambda p: int(p * .52)))
    res = Image.composite(ip, pp, mp.filter(ImageFilter.GaussianBlur(.35))).convert("RGBA"); res.putalpha(da)
    bb = res.getchannel("A").getbbox()
    return res.crop((max(0, bb[0]-6), max(0, bb[1]-6), min(cw, bb[2]+6), min(ch, bb[3]+6))) if bb else res


def align_feet(img):
    s = img.getchannel("A").point(lambda v: 255 if v >= 192 else 0); bb = s.getbbox()
    if not bb: return img
    l, t, r, b = bb; w, h = r - l, b - t; ft = []
    for a0, a1 in ((.07, .31), (.69, .93)):
        es = sorted(bx[3] for x in range(l + int(a0 * w), l + int(a1 * w)) if (bx := s.crop((x, t, x + 1, b)).getbbox()))
        if not es: return img
        ft.append(t + es[int(.8 * (len(es) - 1))])
    sh = min(ft)
    if b - sh > h * .07: return img
    cut = sh - max(1, h // 300); sp = s.crop((0, cut - 1, img.width, cut)).getbbox()
    return img.crop((sp[0], 0, sp[2], cut)) if (sp and sp[0] - l <= w * .02 and r - sp[2] <= w * .02) else img.crop((0, 0, img.width, cut))


def detect_wick(rgba):
    """结合竖直细柱追踪、防纸边过滤与连续底座实心校验定位单蜡烛芯；无可靠蜡烛时返回 None 避免误亮火苗。"""
    w, h = rgba.size; px = rgba.load()
    def is_fg(x, y):
        r, g, b, a = px[x, y]
        if a <= 200: return False
        # 剔除 300g 米白刀模卡纸底边与浅灰阴影环，保留彩色及浅粉细蜡烛
        if r >= g >= b and min(r, g, b) >= 184 and (r - b) <= 32: return False
        return min(r, g, b) < 232 or (max(r, g, b) - min(r, g, b)) > 16
    max_sw = max(18, int(w * .085)); max_cx_drift = max(5, int(w * .02)); min_ch = max(8, int(h * .025))
    chains, active = [], []
    x0_scan, x1_scan = int(w * .24), int(w * .76)
    for y in range(int(h * .02), int(h * .46)):
        segs = []; on = False; s0 = 0
        for x in range(x0_scan, x1_scan):
            if is_fg(x, y):
                if not on: on, s0 = True, x
            elif on: on = False; segs.append((s0, x - 1))
        if on: segs.append((s0, x1_scan - 1))
        merged = []
        for a0, a1 in segs:
            if merged and a0 - merged[-1][1] <= 2: merged[-1] = (merged[-1][0], a1)
            else: merged.append((a0, a1))
        next_act = []
        narrows = [(a0, a1, (a0 + a1) / 2.0, a1 - a0 + 1) for a0, a1 in merged if 1 <= a1 - a0 + 1 <= max_sw]
        used = set()
        for ch in active:
            ly, lcx, lw = ch[-1][0], ch[-1][3], ch[-1][4]
            if y - ly > 3:
                if ch[-1][0] - ch[0][0] + 1 >= min_ch and len(ch) >= 6: chains.append(ch)
                continue
            cand = [(abs(cx - lcx), idx, (y, a0, a1, cx, wd)) for idx, (a0, a1, cx, wd) in enumerate(narrows)
                    if idx not in used and abs(cx - lcx) <= max_cx_drift and wd <= lw * 2.3 + 5]
            if cand:
                _, idx, item = min(cand); used.add(idx); ch.append(item); next_act.append(ch)
            else: next_act.append(ch)
        for idx, (a0, a1, cx, wd) in enumerate(narrows):
            if idx not in used: next_act.append([(y, a0, a1, cx, wd)])
        active = next_act
    for ch in active:
        if ch[-1][0] - ch[0][0] + 1 >= min_ch and len(ch) >= 6: chains.append(ch)
    if chains:
        best_score, best_pt = -1e9, None
        span_side = max(14, int(w * .055)); min_side = max(7, int(w * .025)); gap_rows = max(24, int(h * .12))
        for ch in chains:
            y0, y1 = ch[0][0], ch[-1][0]; ch_h = y1 - y0 + 1
            avg_x = sum(p[3] for p in ch[:6]) / min(6, len(ch)); avg_w = sum(p[4] for p in ch) / len(ch)
            base_cx = ch[-1][3]
            if not (w * .26 <= avg_x <= w * .74): continue
            if abs(base_cx - ch[0][3]) > max(8, int(w * .045)): continue
            # 确认顶端点邻域确为非纸边实心像素
            ax_i = int(round(avg_x))
            if not any(is_fg(xx, yy) for yy in range(max(0, y0), min(h, y0 + 4)) for xx in range(max(0, ax_i - 1), min(w, ax_i + 2))): continue
            center_score = 3.0 * (1.0 - abs(avg_x / w - .5) * 2.0)
            slim_score = min(4.5, ch_h / max(2.0, avg_w))
            has_cake_base = False; consec_base = 0; gap_void = 0; base_top = None
            lx = int(round(base_cx))
            for cy in range(y1 + 1, min(h - 1, y1 + gap_rows)):
                near_n = sum(1 for x in range(max(0, lx - 12), min(w, lx + 13)) if is_fg(x, cy))
                if near_n == 0:
                    gap_void += 1; consec_base = 0
                    if gap_void >= 5: break
                    continue
                l_cnt = sum(1 for x in range(max(0, lx - span_side * 2), max(0, lx - 2)) if is_fg(x, cy))
                r_cnt = sum(1 for x in range(min(w, lx + 3), min(w, lx + span_side * 2 + 1)) if is_fg(x, cy))
                if l_cnt >= min_side and r_cnt >= min_side and (l_cnt + r_cnt) >= max(24, int(avg_w * 2.2)):
                    consec_base += 1
                    if consec_base >= 2:
                        base_top = cy - 1; break
                else:
                    consec_base = 0
            if base_top is not None:
                # 纵深实心体校验：真蛋糕向下至少 h*8.5% 均为实心支撑，淘汰仅 14~20px 厚的上方花环拱顶
                depth_end = min(h - 1, base_top + max(28, int(h * .085)))
                depth_rows = max(1, depth_end - base_top)
                solid_rows = 0
                for dy_i in range(base_top, depth_end):
                    mid_cov = sum(1 for x in range(max(0, lx - span_side), min(w, lx + span_side + 1)) if is_fg(x, dy_i))
                    if mid_cov >= max(14, int(span_side * .8)): solid_rows += 1
                if solid_rows / float(depth_rows) >= .75:
                    has_cake_base = True
            if not has_cake_base: continue
            score = center_score + slim_score + 6.0
            if score > best_score: best_score, best_pt = score, (avg_x, y0)
        if best_pt is not None and best_score >= 6.8:
            return {"leftPct": round(max(24., min(76., best_pt[0] / w * 100.)), 2), "topPct": round(max(2.5, min(44., best_pt[1] / h * 100.)), 2)}
    return None


def make_linen_card(w=520, h=710):
    """纯 Pillow 现场合成 V8.4 实拍级粗纺原麻 3D 高度场棉麻底布、厚鼓滚边凹槽、修长紧勒棉绳锁边与不规则手撕毛边（零外图，耗时 ~0.16s）。"""
    rng = random.Random(20261121)

    # 1. 264x264 无缝颗粒感原麻高度场瓦片（264=3x88 零跨边缝，微斜粒化消弭十字格子，暖沙原麻色系）
    ts = 264
    r0 = random.Random(20261122)
    n3 = ts // 3 + 2
    slub_x = [r0.uniform(-.16, .16) for _ in range(n3)]
    slub_y = [r0.uniform(-.16, .16) for _ in range(n3)]
    col_x = [r0.uniform(-1.0, 1.0) for _ in range(n3)]
    col_y = [r0.uniform(-1.1, 1.1) for _ in range(n3)]
    warp_wobble = [math.sin(y * 2.0 * math.pi / ts * 4.0 + .5) * .62 + math.sin(y * 2.0 * math.pi / ts * 9.0) * .28 for y in range(ts)]
    weft_wobble = [math.sin(x * 2.0 * math.pi / ts * 5.0 + 1.2) * .56 + math.sin(x * 2.0 * math.pi / ts * 11.0) * .24 for x in range(ts)]

    hg = [0.0] * (ts * ts)
    k3 = math.pi / 3.0
    for y in range(ts):
        xw = warp_wobble[y]; sy0 = slub_y[y // 3]; row = y * ts
        for x in range(ts):
            # 相邻微斜错相 + 强局部纤维凸起，使整体呈现斜粒沙感而非呆板直角矩阵
            fx = (x + xw + y * .18) * k3; fy = (y + weft_wobble[x]) * k3
            sxv, syv = math.sin(fx), math.sin(fy)
            wxv, wyv = abs(sxv), abs(syv)
            warp = wxv * (1.0 + .30 * syv) * (1.0 + slub_x[x // 3]) * .80
            weft = wyv * (1.0 - .30 * sxv) * (1.0 + sy0) * 1.10
            top_h = warp if warp >= weft else weft
            hg[row + x] = .50 * top_h + .22 * (warp + weft) + r0.uniform(-.16, .16)

    bf = bytearray(ts * ts * 3)
    k = 0
    for y in range(ts):
        ru = ((y - 1) % ts) * ts; rm = y * ts; rd = ((y + 1) % ts) * ts
        cy = col_y[y // 3]
        for x in range(ts):
            gx = hg[rm + (x + 1) % ts] - hg[rm + (x - 1) % ts]
            gy = hg[rd + x] - hg[ru + x]
            lit = (.68 * gx + .73 * gy) * 20.5
            ao = (hg[rm + x] - .78) * 14.0
            grain = col_x[x // 3] + cy + r0.uniform(-5.2, 5.2)
            if r0.random() < .009: grain -= r0.uniform(11.0, 24.0)
            v = lit + ao + grain
            bf[k] = max(136, min(250, int(223 + v)))
            bf[k + 1] = max(126, min(244, int(214 + v * .96)))
            bf[k + 2] = max(110, min(228, int(197 + v * .89)))
            k += 3
    tile = Image.frombytes("RGB", (ts, ts), bytes(bf))
    base = Image.new("RGB", (w, h))
    for ty in range(0, h, ts):
        for tx in range(0, w, ts): base.paste(tile, (tx, ty))
    base = base.filter(ImageFilter.GaussianBlur(.24))

    # 2. 强立体厚鼓滚边 + 缝线连续勒凹深槽 + 全布自然揉皱明暗层次
    mw, mh_sz = w // 2, h // 2
    mx, my = 38, 40
    hm = Image.new("L", (mw, mh_sz), 178)
    hd = ImageDraw.Draw(hm)
    hd.rectangle([mx // 2 + 3, my // 2 + 3, mw - mx // 2 - 3, mh_sz - my // 2 - 3], fill=124)
    hd.rectangle([mx // 2, my // 2, mw - mx // 2, mh_sz - my // 2], outline=64, width=6)
    hd.line([(int(mw * .15), int(mh_sz * .64)), (int(mw * .52), int(mh_sz * .40)), (int(mw * .86), int(mh_sz * .25))], fill=140, width=28, joint="curve")
    hd.line([(int(mw * .12), int(mh_sz * .28)), (int(mw * .48), int(mh_sz * .54)), (int(mw * .86), int(mh_sz * .74))], fill=112, width=28, joint="curve")
    hm_full = hm.filter(ImageFilter.GaussianBlur(6.5)).resize((w, h), Image.Resampling.BICUBIC)

    cloud = Image.frombytes("L", (16, 22), bytes(rng.randint(102, 152) for _ in range(16 * 22)))
    cloud = cloud.resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(24))
    hm_mix = Image.blend(hm_full, cloud, .28)

    gx_up = ImageChops.subtract(ImageChops.offset(hm_mix, 4, 0), ImageChops.offset(hm_mix, -4, 0))
    gx_dn = ImageChops.subtract(ImageChops.offset(hm_mix, -4, 0), ImageChops.offset(hm_mix, 4, 0))
    gy_up = ImageChops.subtract(ImageChops.offset(hm_mix, 0, 4), ImageChops.offset(hm_mix, 0, -4))
    gy_dn = ImageChops.subtract(ImageChops.offset(hm_mix, 0, -4), ImageChops.offset(hm_mix, 0, 4))
    m_lit = ImageChops.add(gx_up.point(lambda p: int(p * .62)), gy_up.point(lambda p: int(p * .68)))
    m_drk = ImageChops.add(gx_dn.point(lambda p: int(p * .60)), gy_dn.point(lambda p: int(p * .65)))
    hi_h = hm_mix.point(lambda p: max(0, int((p - 126) * .45)))
    lo_h = hm_mix.point(lambda p: max(0, int((126 - p) * .56)))
    lit_all = ImageChops.add(m_lit, hi_h)
    drk_all = ImageChops.add(m_drk, lo_h)
    base = ImageChops.add(base, Image.merge("RGB", (lit_all, lit_all.point(lambda p: int(p * .97)), lit_all.point(lambda p: int(p * .91)))))
    base = ImageChops.subtract(base, Image.merge("RGB", (drk_all, drk_all.point(lambda p: int(p * 1.03)), drk_all.point(lambda p: int(p * 1.09)))))

    # 从左上方打入柔和温暖侧光、向右下方自然微沉
    glow = Image.new("L", (mw, mh_sz), 0)
    ImageDraw.Draw(glow).ellipse([-int(mw * .24), -int(mh_sz * .18), int(mw * .82), int(mh_sz * .70)], fill=16)
    g_rgb = glow.filter(ImageFilter.GaussianBlur(28)).resize((w, h), Image.Resampling.BICUBIC)
    base = ImageChops.add(base, Image.merge("RGB", (g_rgb, g_rgb, g_rgb.point(lambda p: int(p * .92)))))

    # 3. 连贯深凹缝线沟 + 手工斜倾修长粗白棉绳（告别臃肿小面包块）
    segs = []
    for cnt, p0, p1, horiz, fixed, inv in (
        (11, mx + 6, w - mx - 6, True, my, -1), (11, mx + 6, w - mx - 6, True, h - my, 1),
        (16, my + 6, h - my - 6, False, mx, -1), (16, my + 6, h - my - 6, False, w - mx, 1),
    ):
        step = (p1 - p0) / cnt; sl = step * .79
        for i in range(cnt):
            a = p0 + i * step + (step - sl) * .5 + rng.uniform(-1.5, 1.5)
            b = a + sl + rng.uniform(-2.0, 2.0)
            # 每针略微手工倾斜 1.5~3px，并带微小弧拱
            tilt = rng.uniform(-1.8, 1.8)
            j1, j2 = rng.uniform(-1.4, 1.4) + tilt, rng.uniform(-1.4, 1.4) - tilt
            arch = rng.uniform(.8, 2.0) * inv
            thick = rng.uniform(.88, 1.14)
            if horiz: segs.append((a, fixed + j1, (a + b) * .5, fixed + (j1 + j2) * .5 + arch, b, fixed + j2, thick))
            else: segs.append((fixed + j1, a, fixed + (j1 + j2) * .5 + arch, (a + b) * .5, fixed + j2, b, thick))

    def qbez(x0, y0, xm, ym, x1, y1, t):
        cx, cy = 2.0 * xm - .5 * (x0 + x1), 2.0 * ym - .5 * (y0 + y1)
        u = 1.0 - t
        return u * u * x0 + 2.0 * u * t * cx + t * t * x1, u * u * y0 + 2.0 * u * t * cy + t * t * y1

    # 沿整条缝线路径压出轻柔连续勒痕沟（主要暗深集中于针眼凹洞与线身投影）
    groove = Image.new("RGBA", (w, h), (82, 66, 50, 0)); gr_d = ImageDraw.Draw(groove)
    gr_d.rectangle([mx, my, w - mx, h - my], outline=(82, 66, 50, 62), width=7)
    dent_l = Image.new("RGBA", (w, h), (62, 47, 34, 0)); dent_d = ImageDraw.Draw(dent_l)
    sh_l = Image.new("RGBA", (w, h), (70, 56, 42, 0)); sh_d = ImageDraw.Draw(sh_l)
    st_l = Image.new("RGBA", (w, h), (235, 228, 212, 0)); st_d = ImageDraw.Draw(st_l)

    for x0, y0, xm, ym, x1, y1, thick in segs:
        ln = max(1.0, math.hypot(x1 - x0, y1 - y0))
        ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
        for ex, ey, sgn in ((x0, y0, 1.0), (x1, y1, -1.0)):
            dent_d.line([(ex - ux * sgn * 1.5, ey - uy * sgn * 1.5), (ex + ux * sgn * 4.5, ey + uy * sgn * 4.5)], fill=(68, 52, 36, 152), width=4)
            dent_d.ellipse([ex - 2.6, ey - 2.6, ex + 2.6, ey + 2.6], fill=(56, 42, 28, 175))
        pts = [qbez(x0, y0, xm, ym, x1, y1, k / 12.0) for k in range(13)]
        sh_d.line([(px + 1.4, py + 2.6) for px, py in pts], fill=(66, 52, 38, 140), width=round(5.8 * thick), joint="curve")
        for k in range(12):
            t_mid = (k + .5) / 12.0
            prof = .38 + .62 * math.sin(t_mid * math.pi) ** .46
            p_a, p_b = pts[k], pts[k + 1]
            # 顺滑圆润本白粗棉绳（暖棕底边 + 本白饱满主体 + 连续柔亮脊，无生硬切分纹）
            st_d.line([p_a, p_b], fill=(162, 148, 128, 238), width=max(2, round(6.0 * thick * prof)))
            st_d.line([(p_a[0] - .35, p_a[1] - .45), (p_b[0] - .35, p_b[1] - .45)], fill=(235, 227, 210, 255), width=max(2, round(4.8 * thick * prof)))
            st_d.line([(p_a[0] - .85, p_a[1] - 1.05), (p_b[0] - .85, p_b[1] - 1.05)], fill=(254, 251, 245, 228), width=max(1, round(2.2 * thick * prof)))

    comp = Image.alpha_composite(
        Image.alpha_composite(
            Image.alpha_composite(
                Image.alpha_composite(base.convert("RGBA"), groove.filter(ImageFilter.GaussianBlur(3.4))),
                dent_l.filter(ImageFilter.GaussianBlur(2.3)),
            ),
            sh_l.filter(ImageFilter.GaussianBlur(1.9)),
        ),
        st_l.filter(ImageFilter.GaussianBlur(.42)),
    )

    # 4. 更有机不规则的手撕厚布边缘与圆润四角（大凹凸波 + 碎缺口 + 密集短棉絮）
    poly = []
    def walk_edge(cnt_steps, fixed_base, span_start, span_end, horiz, phase):
        off = 0.0
        for s in range(cnt_steps):
            t = s / max(1, cnt_steps - 1)
            # 四角处微圆钝内收，中段自由高低波浪起落
            c_round = (1.0 - math.sin(t * math.pi) ** .18) * 3.5
            off = off * .72 + rng.uniform(-1.9, 1.9)
            wave = math.sin(t * math.pi * 3.8 + phase) * 3.2 + math.sin(t * math.pi * 11.2 + phase * 1.9) * 1.5
            inward = -c_round if fixed_base > 100 else c_round
            val = fixed_base + max(-8.0, min(8.0, off + wave)) + inward
            pos = span_start + (span_end - span_start) * t
            poly.append((round(pos), round(val)) if horiz else (round(val), round(pos)))

    walk_edge(160, 15, 16, w - 17, True, 0.4)
    walk_edge(220, w - 17, 16, h - 17, False, 1.9)
    walk_edge(160, h - 17, w - 17, 16, True, 3.2)
    walk_edge(220, 15, h - 17, 16, False, 4.7)

    edge_cotton = Image.new("RGBA", (w, h), (234, 226, 210, 0))
    ImageDraw.Draw(edge_cotton).line(poly + [poly[0]], fill=(241, 234, 219, 220), width=7)
    comp_rgb = Image.alpha_composite(Image.new("RGBA", (w, h), (232, 224, 208, 255)), comp)
    rim_sh = Image.new("RGBA", (w, h), (138, 122, 102, 0))
    br_pts = poly[160:160 + 220 + 160]
    ImageDraw.Draw(rim_sh).line(br_pts, fill=(138, 122, 102, 145), width=7)
    comp_rgb = Image.alpha_composite(Image.alpha_composite(comp_rgb, edge_cotton.filter(ImageFilter.GaussianBlur(1.9))), rim_sh.filter(ImageFilter.GaussianBlur(2.6)))

    am = Image.new("L", (w, h), 0); ad = ImageDraw.Draw(am)
    ad.polygon(poly, fill=255)
    npts = len(poly)
    for k in range(npts):
        px0, py0 = poly[k]
        px_p, py_p = poly[(k - 2) % npts]; px_n, py_n = poly[(k + 2) % npts]
        tx, ty = px_n - px_p, py_n - py_p; tl_v = max(1.0, math.hypot(tx, ty))
        ox, oy = ty / tl_v, -tx / tl_v
        for _ in range(2):
            ang_j = rng.uniform(-.95, .95)
            dx0 = ox * math.cos(ang_j) - oy * math.sin(ang_j); dy0 = ox * math.sin(ang_j) + oy * math.cos(ang_j)
            fl = rng.uniform(1.4, 4.2)
            ad.line([(px0 - ox * 1.2, py0 - oy * 1.2), (px0 + dx0 * fl, py0 + dy0 * fl)], fill=rng.randint(120, 234), width=1 if rng.random() > .32 else 2)
        if rng.random() < .22:
            fl2 = rng.uniform(3.0, 6.2)
            ex = px0 + ox * fl2 + rng.uniform(-2.4, 2.4); ey = py0 + oy * fl2 + rng.uniform(-2.4, 2.4)
            mx_f = (px0 + ex) * .5 + rng.uniform(-1.3, 1.3); my_f = (py0 + ey) * .5 + rng.uniform(-1.3, 1.3)
            ad.line([(px0, py0), (mx_f, my_f), (ex, ey)], fill=rng.randint(85, 175), width=1, joint="curve")

    out = comp_rgb.convert("RGBA")
    out.putalpha(am.filter(ImageFilter.GaussianBlur(.52)))
    return out


def erode(m, r):
    for _ in range(max(1, r // 2)): m = m.filter(ImageFilter.MinFilter(5))
    return m


def detect_tree_lights(rgba):
    """基于 Alpha 内芯实心校验定位顶星与树冠星灯（兼容偏心歪斜树尖、白雪树与分叉树，0 悬空）。"""
    w, h = rgba.size; solid = rgba.convert("RGBA").getchannel("A").point(lambda p: 255 if p > 215 else 0)
    sbb = solid.getbbox()
    if not sbb: return {"topStar": None, "lights": []}
    spx = solid.load()
    tr = max(4, min(10, int(min(w, h) * .02))); tm = erode(solid, tr)
    if not tm.getbbox(): tm = solid
    tpx = tm.load()
    def scan(pm, y):
        sg, on, s0 = [], False, 0
        for x in range(w):
            if pm[x, y] > 128:
                if not on: on, s0 = True, x
            elif on: on = False; sg.append((s0, x - 1))
        if on: sg.append((s0, w - 1))
        return sg
    def scan_peaks(pm):
        out = []
        for y in range(int(h * .01), int(h * .35)):
            ss = scan(pm, y)
            if ss:
                lg = max(ss, key=lambda s: s[1] - s[0])
                if lg[1] - lg[0] >= 2:
                    out.append((y, (lg[0] + lg[1]) / 2.0))
                    if len(out) >= 5: break
        return out
    def is_solid(pm, ix, iy): return 0 <= ix < w and 0 <= iy < h and pm[ix, iy] > 128
    def snap_solid(xf, yf):
        ix, iy = int(round(max(0., min(w - 1., xf)))), int(round(max(0., min(h - 1., yf))))
        mr = max(20, int(min(w, h) * .12))
        for pm in (tpx, spx):
            if is_solid(pm, ix, iy): return float(ix), float(iy)
            for r in range(1, mr + 1):
                best = None
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if abs(dx) != r and abs(dy) != r: continue
                        nx, ny = ix + dx, iy + dy
                        if is_solid(pm, nx, ny):
                            d2 = dx * dx + dy * dy
                            if best is None or d2 < best[0]: best = (d2, nx, ny)
                if best is not None: return float(best[1]), float(best[2])
        return None
    pks = scan_peaks(tpx) or scan_peaks(spx); ts = None
    if pks:
        cx = max(w * .04, min(w * .96, sum(p[1] for p in pks) / len(pks)))
        cy = max(h * .025, min(h * .32, min(int(h * .30), pks[0][0] + max(2, int(h * .012)))))
        snapped = snap_solid(cx, cy)
        if snapped is not None:
            sx, sy = snapped
            lp, tp = round(max(4., min(96., sx / w * 100.)), 2), round(max(2.5, min(32., sy / h * 100.)), 2)
            vx, vy = min(w - 1, max(0, int(round(lp / 100. * w)))), min(h - 1, max(0, int(round(tp / 100. * h))))
            if is_solid(spx, vx, vy): ts = {"leftPct": lp, "topPct": tp}
            else:
                lp2, tp2 = round(max(4., min(96., int(sx / w * 10000.) / 100.)), 2), round(max(2.5, min(32., int(sy / h * 10000.) / 100.)), 2)
                if is_solid(spx, min(w - 1, max(0, int(round(lp2 / 100. * w)))), min(h - 1, max(0, int(round(tp2 / 100. * h))))):
                    ts = {"leftPct": lp2, "topPct": tp2}
    cm = erode(solid, max(12, min(22, int(min(w, h) * .036))))
    if not cm.getbbox(): cm = erode(solid, max(6, tr))
    cpx = cm.load()
    def ok_pt(xf, yf):
        ix, iy = int(round(xf)), int(round(yf))
        return 2 <= ix < w - 2 and 2 <= iy < h - 2 and sum(1 for dy in range(-2, 3) for dx in range(-2, 3) if cpx[ix+dx, iy+dy] > 128) >= 22
    ct, cb, ls, md2, idx = (ts["topPct"] / 100. * h if ts else float(sbb[1])), h * .74, [], max(12., min(w, h) * .075) ** 2, 0
    for lr, cnt in zip((.18, .36, .54, .72, .90), (2, 2, 3, 3, 3)):
        yb = int(round(ct + (cb - ct) * lr))
        if not (4 < yb < h - 4): continue
        sgs = [s for s in scan(cpx, yb) if s[1] - s[0] >= max(8, int(w * .035))]
        if not sgs: continue
        tw = sum(s[1] - s[0] for s in sgs)
        for si, (x0, x1) in enumerate(sgs):
            sw = x1 - x0; q = max(1, cnt // len(sgs)) if (si == 0 and len(sgs) >= 2) else max(1, round(cnt * sw / max(1, tw)))
            pd = min(sw * .22, max(4., w * .02)); uw = max(1., sw - 2 * pd)
            for k in range(q):
                cx = x0 + pd + uw * (.5 if q == 1 else .15 + .7 * k / (q - 1))
                cy = min(cb, max(ct + 8, yb + ((-1) ** (idx + k)) * min(6., h * .012)))
                pt = next(((cx, ty) for ty in (cy, float(yb), float(yb - 4), float(yb + 4)) if ok_pt(cx, ty)), None)
                if not pt and ok_pt((x0 + x1) / 2., float(yb)): pt = ((x0 + x1) / 2., float(yb))
                if not pt or any((pt[0] - p["_x"]) ** 2 + (pt[1] - p["_y"]) ** 2 < md2 for p in ls): continue
                ls.append({"_x": pt[0], "_y": pt[1], "leftPct": round(max(4., min(96., pt[0] / w * 100.)), 2), "topPct": round(max(5., min(88., pt[1] / h * 100.)), 2),
                           "size": 10 if idx % 3 == 0 else 8, "delay": round((idx * .37) % 2.2, 2), "duration": round(1.55 + (idx % 4) * .32, 2), "warm": idx % 2 == 0})
                idx += 1
    for p in ls: p.pop("_x", None); p.pop("_y", None)
    return {"topStar": ts, "lights": ls[:13]}


def fit_surf(path, sz, max_crop_ratio=1.45, mode="auto"):
    """按目标比例适配封面/内页：支持 auto（超阈值自动保边扩纸底）、contain 与 crop。"""
    img = Image.open(path).convert("RGB"); sw, sh = img.size; dw, dh = sz
    rd = max((sw / float(sh)) / (dw / float(dh)), (dw / float(dh)) / (sw / float(sh))) if sw > 0 and sh > 0 else 1.0
    if mode == "contain" or (mode == "auto" and rd > max_crop_ratio):
        print(f"[提示] '{os.path.basename(path)}' 比例差 {rd:.2f}x，已保边扩纸底保留完整画面。", file=sys.stderr)
        px = img.load()
        sm = [px[x, y] for x in range(0, sw, max(1, sw // 24)) for y in (0, sh - 1)] + [px[x, y] for y in range(0, sh, max(1, sh // 24)) for x in (0, sw - 1)]
        bg = tuple(int(sum(c[i] for c in sm) / len(sm)) for i in range(3)) if sm else (246, 241, 232)
        cv = Image.new("RGB", sz, bg); ct = ImageOps.contain(img, sz, Image.Resampling.LANCZOS)
        cv.paste(ct, ((dw - ct.width) // 2, (dh - ct.height) // 2)); return cv
    return ImageOps.fit(img, sz, Image.Resampling.LANCZOS)


def palette(cov):
    def h2x(hd, sp, lp):
        r, g, b = colorsys.hls_to_rgb((hd % 360.) / 360., max(0., min(1., lp / 100.)), max(0., min(1., sp / 100.)))
        return f"#{int(round(r*255)):02x}{int(round(g*255)):02x}{int(round(b*255)):02x}"
    bks = [[0, 0, 0, 0] for _ in range(12)]; tr = tg = tb = cnt = 0
    for r, g, b in cov.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR).getdata():
        tr += r; tg += g; tb += b; cnt += 1
        h, l, s = colorsys.rgb_to_hls(r / 255., g / 255., b / 255.)
        if s > .18 and .18 < l < .84:
            bk = bks[int((h * 360.) // 30) % 12]; bk[0] += 1; bk[1] += r; bk[2] += g; bk[3] += b
    bks.sort(key=lambda x: x[0], reverse=True)
    p1 = bks[0] if bks[0][0] > 0 else [1, 79, 115, 72]; p2 = bks[1] if bks[1][0] > 4 else [1, 181, 73, 107]
    ph, pl, ps = colorsys.rgb_to_hls(p1[1]/p1[0]/255., p1[2]/p1[0]/255., p1[3]/p1[0]/255.)
    sh, sl, ss = colorsys.rgb_to_hls(p2[1]/p2[0]/255., p2[2]/p2[0]/255., p2[3]/p2[0]/255.)
    ah = colorsys.rgb_to_hls(tr/cnt/255., tg/cnt/255., tb/cnt/255.)[0] * 360.
    phd, shd = ph * 360., sh * 360.; cool = 165. <= phd <= 265.; th = ah if cool else min(42., max(28., ah))
    return {"styleName": "定制同系艺术风格", "tableInner": h2x(th, 22 if cool else 34, 86), "tableOuter": h2x(th, 18 if cool else 28, 74),
            "paperCream": "#faf6ec", "primaryAccent": h2x(phd, min(58, max(30, ps*100)), min(46, max(32, pl*100))),
            "secondaryAccent": h2x(shd, min(65, max(34, ss*100)), min(58, max(38, sl*100))),
            "waxSealColor": h2x(shd, 62, 44) if (shd < 35 or shd > 320) else "#b9382e", "filterCss": "none"}


def uri(img, q=86, md=None):
    w = img.copy()
    if md and max(w.size) > md: w.thumbnail((md, md), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    try: w.save(buf, format="WEBP", quality=q, method=4); mt = "image/webp"
    except Exception:
        buf = io.BytesIO()
        if "A" in w.getbands(): w.save(buf, format="PNG", optimize=True); mt = "image/png"
        else: w.convert("RGB").save(buf, format="JPEG", quality=q, optimize=True); mt = "image/jpeg"
    return f"data:{mt};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def sim(p1, p2):
    a = list(Image.open(p1).convert("RGB").resize((64, 64), Image.Resampling.BILINEAR).getdata())
    b = list(Image.open(p2).convert("RGB").resize((64, 64), Image.Resampling.BILINEAR).getdata())
    return round(1. - sum(abs(x[0]-y[0]) + abs(x[1]-y[1]) + abs(x[2]-y[2]) for x, y in zip(a, b)) / (64*64*765.), 4)


def check_character_redraw(chr_p, pt_p, strict):
    """核查人物图四周是否干净白底/透明且不与真人原照高度雷同，拦截直接传入带背景或未重绘写真照。"""
    raw = Image.open(chr_p)
    if max(raw.size) > 320: raw.thumbnail((320, 320), Image.Resampling.BILINEAR)
    w, h = raw.size
    has_trans_border = False
    if raw.mode in ("RGBA", "LA", "PA") or "transparency" in raw.info:
        ac = raw.convert("RGBA").getchannel("A"); apx = ac.load()
        if ac.getextrema()[0] < 20:
            st = max(1, min(w, h) // 48)
            bs = [apx[x, y] for x in range(0, w, st) for y in (0, h - 1)] + [apx[x, y] for y in range(0, h, st) for x in (0, w - 1)]
            if bs and sum(1 for v in bs if v < 40) / float(len(bs)) >= .50: has_trans_border = True
    if not has_trans_border:
        rgb = raw.convert("RGB"); px = rgb.load(); bd = max(3, min(w, h) // 32)
        tot = white = 0
        for y in range(h):
            for x in range(w):
                if x < bd or x >= w - bd or y < bd or y >= h - bd:
                    r, g, b = px[x, y]; tot += 1
                    if min(r, g, b) >= 224 and max(r, g, b) - min(r, g, b) <= 26: white += 1
        wr = white / float(max(1, tot))
        if wr < .60:
            msg = f"人物图四周白底占比仅 {wr*100:.1f}%，疑似直接传入带背景照片"
            if strict: raise SystemExit(f"错误：{msg}，已拦截打包。")
            print(f"[警告] {msg}。", file=sys.stderr)
    if pt_p and os.path.isfile(pt_p) and sim(chr_p, pt_p) >= .94:
        msg = "人物图与真人原照高度雷同，疑似未进行手绘重绘"
        if strict: raise SystemExit(f"错误：{msg}，已拦截打包。")
        print(f"[警告] {msg}。", file=sys.stderr)


def parse_wick_pos(raw):
    parts = [p.strip() for p in re.split(r"[,，\s]+", str(raw or "").strip()) if p.strip()]
    if len(parts) != 2: raise ValueError("格式须为 LEFT,TOP")
    lp, tp = float(parts[0]), float(parts[1])
    if not (1.0 <= lp <= 99.0 and 1.0 <= tp <= 99.0): raise ValueError("坐标百分比须在 1~99 之间")
    return {"leftPct": round(lp, 2), "topPct": round(tp, 2)}


def norm_b(raw, occ):
    if not isinstance(raw, dict): raise ValueError("祝福语必须是 JSON 对象")
    xm = occ == "christmas"
    dl = ["雪花轻落窗台，圣诞灯火正暖", "愿今年所有的温柔与期盼", "都化作冬日里的星光与好运", "平安顺遂，温暖常伴左右"] if xm else \
         ["又长大一岁啦，愿新岁的每一天", "都有温暖的风吹散烦恼", "愿你永远被爱包围", "平安顺遂，自在闪耀"]
    lv = raw.get("lines")
    if lv is None: ls = dl
    elif isinstance(lv, str): ls = [p.strip() for p in re.split(r"[\r\n。！？；;]+", lv) if p.strip()] or dl
    elif isinstance(lv, list): ls = [str(x or "").strip() for x in lv if str(x or "").strip()] or dl
    else: raise ValueError("lines 须为字符串或数组")
    return {"recipient": str(raw.get("recipient") or "亲爱的朋友：").strip(), "lines": ls,
            "closing": str(raw.get("closing") or ("圣诞快乐，冬日安暖！" if xm else "生日快乐，万事胜意！")).strip(),
            "signature": str(raw.get("signature") or "你的好友").strip(), "subSignature": str(raw.get("subSignature") or "").strip()}


def assemble(cfg):
    ps = [RES / n for n in ("shell_p1.css", "shell_p2.html", "shell_p3.js", "shell_p4.js")]
    for p in ps:
        if not p.is_file(): raise FileNotFoundError(f"缺少母版分片: {p}")
    c, d, j3, j4 = (p.read_text(encoding="utf-8") for p in ps)
    js = json.dumps(cfg, ensure_ascii=False).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    return f'<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/><title>手绘立体纸艺贺卡</title><style>\n{c}\n</style></head><body><script>window.CARD_CONFIG=/*__CARD_CONFIG_START__*/{js}/*__CARD_CONFIG_END__*/;</script>\n{d}\n<script>(function(){{\n{j3}\n{j4}\n}})();</script></body></html>\n'


def main():
    ap = argparse.ArgumentParser(description="立体贺卡纯本地刀模抠图与正宗母版打包器")
    for k in ("--work-dir","--cover","--character","--portrait","--inside","--inside-top","--inside-bottom","--inside-left","--inside-right","--arch","--cake","--tree","--style-ref","--style-json","--blessing","--recipient","--lines-text","--closing","--signature","--sub-signature","--card-id","--wick-pos"): ap.add_argument(k)
    ap.add_argument("--occasion", choices=("birthday","christmas"), default="birthday")
    ap.add_argument("--fold", choices=("horizontal","vertical"), default="horizontal")
    ap.add_argument("--cover-fit", choices=("auto","contain","crop"), default="auto")
    ap.add_argument("--strict-redraw-check", action="store_true"); ap.add_argument("--allow-draft", action="store_true"); ap.add_argument("--allow-missing-wick", action="store_true"); ap.add_argument("--output", required=True)
    a = ap.parse_args(); wd, vert, xm = (Path(a.work_dir) if a.work_dir else None), a.fold == "vertical", a.occasion == "christmas"
    for flag, val in (("--cover",a.cover),("--character",a.character),("--portrait",a.portrait),("--inside",a.inside),("--inside-top",a.inside_top),("--inside-bottom",a.inside_bottom),("--inside-left",a.inside_left),("--inside-right",a.inside_right),("--arch",a.arch),("--cake",a.cake),("--tree",a.tree),("--style-ref",a.style_ref),("--style-json",a.style_json),("--blessing",a.blessing)):
        if val and not os.path.isfile(val): ap.error(f"指定的 {flag} 文件不存在: {val}")
    cov = a.cover or (find1(wd,"cover_vertical_raw","cover_4x3_raw","cover_raw") if vert else find1(wd,"cover_raw","cover_3x4_raw"))
    chr_p = a.character or find1(wd,"character_raw")
    pt_p = a.portrait or find1(wd,"portrait","photo","selfie")
    ins = a.inside or (find1(wd,"inside_vertical_raw","inside_2x3_raw") if vert else find1(wd,"inside_raw"))
    tp, bp = a.inside_top or (find1(wd,"inside_top") if vert else None), a.inside_bottom or (find1(wd,"inside_bottom") if vert else None)
    il, ir, ar = a.inside_left or find1(wd,"inside_left"), a.inside_right or find1(wd,"inside_right"), a.arch or find1(wd,"arch_raw","christmas_arch_raw")
    if xm:
        if a.cake: ap.error("圣诞模式禁止传 --cake")
        pr = a.tree or find1(wd,"tree_raw","christmas_tree_raw")
        if not pr or not os.path.isfile(pr): ap.error("圣诞模式缺少 --tree 或 tree_raw.png")
    else:
        if a.tree: ap.error("生日模式请传 --cake")
        pr = a.cake or find1(wd,"cake_raw")
        if not pr or not os.path.isfile(pr): ap.error("生日模式缺少 --cake 或 cake_raw.png")
    if not cov or not os.path.isfile(cov): ap.error("缺少封面 --cover")
    if not chr_p or not os.path.isfile(chr_p): ap.error("缺少人物 --character")
    if vert and (tp or bp) and not (tp and bp and os.path.isfile(tp) and os.path.isfile(bp)): ap.error("上下拆页须同时提供 --inside-top 与 --inside-bottom")
    if not vert and (il or ir) and not (il and ir and os.path.isfile(il) and os.path.isfile(ir)): ap.error("左右拆页须同时提供 --inside-left 与 --inside-right")
    if vert and not (tp and bp) and not (ins and os.path.isfile(ins)): ap.error("上下翻折版需要 --inside 或上下内页")
    if not a.allow_draft:
        if not vert and not (il and ir) and not (ins and os.path.isfile(ins)): ap.error("左右横版缺少展开内页（--inside 或成对 --inside-left/--inside-right）")
        if not ar or not os.path.isfile(ar): ap.error("缺少后景花环拱门（--arch 或工作目录 arch_raw）")

    rf = a.style_ref or find1(wd,"style_ref")
    if a.strict_redraw_check and not (rf and os.path.isfile(rf)): ap.error("--strict-redraw-check 需要 --style-ref")
    if rf and os.path.isfile(rf) and sim(cov, rf) >= .96:
        if a.strict_redraw_check: raise SystemExit("错误：封面与参考图高度雷同，已拦截打包。")
        print("[警告] 封面与参考图相似度过高。", file=sys.stderr)
    check_character_redraw(chr_p, pt_p, a.strict_redraw_check)

    manual_wk = None
    if a.wick_pos:
        if xm: ap.error("圣诞模式禁止传 --wick-pos")
        try: manual_wk = parse_wick_pos(a.wick_pos)
        except ValueError as e: ap.error(f"无效 --wick-pos: {e}")

    cim = fit_surf(cov, (1000,750) if vert else (750,1000), max_crop_ratio=1.06, mode=a.cover_fit); cov_u, thm = uri(cim, 88), palette(cim)
    sp = a.style_json or (str(wd / "style_profile.json") if wd and (wd / "style_profile.json").is_file() else None)
    if sp and os.path.isfile(sp):
        try:
            st = json.loads(Path(sp).read_text(encoding="utf-8")).get("styleTheme")
            if isinstance(st, dict): thm.update({k: v for k, v in st.items() if v})
        except Exception: pass

    cst = standee(chr_p, 13, 820, False); ok, rt = check_vis(cst)
    if not ok: raise SystemExit(f"错误：人物图为空白（占比 {rt*100:.2f}%）")
    chr_u = uri(cst, 88, 760)
    ilu = iru = ""
    if vert and tp and bp: ilu, iru = uri(fit_surf(tp,(1000,750)),86), uri(fit_surf(bp,(1000,750)),86)
    elif not vert and il and ir and os.path.isfile(il) and os.path.isfile(ir): ilu, iru = uri(fit_surf(il,(700,934)),86), uri(fit_surf(ir,(700,934)),86)
    elif ins and os.path.isfile(ins):
        si = fit_surf(ins, (1000,1500) if vert else (1400,934))
        ilu, iru = (uri(si.crop((0,0,1000,750)),86), uri(si.crop((0,750,1000,1500)),86)) if vert else (uri(si.crop((0,0,700,934)),86), uri(si.crop((700,0,1400,934)),86))
    aru = ""
    if ar and os.path.isfile(ar):
        ast = standee(ar, 10, 920, True)
        if vert: ast = align_feet(ast)
        ok, rt = check_vis(ast)
        if not ok: raise SystemExit(f"错误：拱门图为空白（占比 {rt*100:.2f}%）")
        aru = uri(ast, 86, 880)
    pst = standee(pr, 11, 760, False); ok, rt = check_vis(pst)
    if not ok: raise SystemExit(f"错误：道具图为空白（占比 {rt*100:.2f}%）")
    tl, pru = (detect_tree_lights(pst) if xm else None), uri(pst, 88, 680)
    if xm:
        wk = {"leftPct": 44.6, "topPct": 7.5}
    elif manual_wk is not None:
        wk = manual_wk
    else:
        wk = detect_wick(pst)
        if wk is None:
            if a.strict_redraw_check and not a.allow_missing_wick:
                raise SystemExit("错误：未能在生日蛋糕中检测到可信蜡烛芯（疑似缺蜡烛或被上方花环遮挡），请重画清晰单蜡烛无火蛋糕，或传入 --wick-pos / --allow-missing-wick。")
            print("[警告] 未能在生日蛋糕中检测到可信蜡烛芯，已隐藏动态烛火（仍保留轻点与长按许愿交互）。", file=sys.stderr)
    lin_u = uri(make_linen_card(), 78)

    rb = {}; bpj = a.blessing or (str(wd / "blessing.json") if wd and (wd / "blessing.json").is_file() else None)
    if bpj and os.path.isfile(bpj):
        ld = json.loads(Path(bpj).read_text(encoding="utf-8"))
        if not isinstance(ld, dict): raise SystemExit("错误：blessing.json 顶层须为 JSON 对象")
        rb = ld
    for fk, bk in (("recipient","recipient"),("closing","closing"),("signature","signature"),("sub_signature","subSignature")):
        if getattr(a, fk) is not None: rb[bk] = getattr(a, fk)
    if a.lines_text is not None: rb["lines"] = a.lines_text.replace("\\n", "\n")
    try: bcfg = norm_b(rb, a.occasion)
    except ValueError as e: raise SystemExit(f"错误：祝福语无效：{e}")

    ah = hashlib.sha256()
    for s in (a.occasion, a.fold, cov_u, chr_u, ilu, iru, pru, aru): ah.update(s.encode("utf-8")); ah.update(b"|")
    ad, out_p = ah.hexdigest(), Path(a.output)
    if (a.card_id or "").strip(): cid = re.sub(r"[^A-Za-z0-9_-]","",a.card_id.strip())[:24] or uuid.uuid4().hex[:12]
    elif wd is not None:
        wd.mkdir(parents=True, exist_ok=True); idf = wd / ".card_id"
        lid = re.sub(r"[^A-Za-z0-9_-]","",idf.read_text(encoding="utf-8").strip())[:24] if idf.is_file() else ""
        if not lid:
            lid = uuid.uuid4().hex[:12]
            try: idf.write_text(lid, encoding="utf-8")
            except OSError: pass
        cid = hashlib.sha256(f"{lid}|{ad}".encode("utf-8")).hexdigest()[:16]
    else:
        cid = hashlib.sha256(f"{ad}|{out_p.resolve()}|{json.dumps(bcfg,ensure_ascii=False,sort_keys=True)}".encode("utf-8")).hexdigest()[:16]

    cfg = {"cardId":cid,"occasion":a.occasion,"fold":a.fold,"coverImageUrl":cov_u,"characterImageUrl":chr_u,"insideLeftUrl":ilu,"insideRightUrl":iru,"cakeTableUrl":pru,"archUrl":aru,"linenImageUrl":lin_u,"cakeWickPos":wk,"styleTheme":thm,"blessing":bcfg}
    if tl is not None: cfg["treeLights"] = tl
    out_p.parent.mkdir(parents=True, exist_ok=True); out_p.write_text(assemble(cfg), encoding="utf-8")
    print(f"[OK] {'圣诞' if xm else '生日'}立体贺卡（{'4:3上下' if vert else '左右横版'}）-> {out_p} ({out_p.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8"); main()
