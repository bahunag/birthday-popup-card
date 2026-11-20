"""立体贺卡纯本地刀模抠图与正宗母版拼接器（V8.1 云端直装版，仅依赖 Pillow，零联网零密钥）"""
import argparse, base64, colorsys, hashlib, io, json, os, re, sys, uuid
from collections import deque
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter, ImageOps

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
    w, h = rgba.size; px = rgba.load(); pts = []
    for y in range(int(h * .02), int(h * .24)):
        xs = [x for x in range(int(w * .22), int(w * .78)) if px[x, y][3] > 200 and (min(px[x, y][:3]) < 232 or max(px[x, y][:3]) - min(px[x, y][:3]) > 16)]
        if 2 <= len(xs) <= int(w * .16):
            pts.append((y, sum(xs) / len(xs)))
            if len(pts) >= 8: break
    if not pts: return {"leftPct": 44.6, "topPct": 7.5}
    return {"leftPct": round(max(28., min(72., sum(p[1] for p in pts) / len(pts) / w * 100.)), 2), "topPct": round(max(3.5, min(20., pts[0][0] / h * 100.)), 2)}


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
    for k in ("--work-dir","--cover","--character","--inside","--inside-top","--inside-bottom","--inside-left","--inside-right","--arch","--cake","--tree","--style-ref","--style-json","--blessing","--recipient","--lines-text","--closing","--signature","--sub-signature","--card-id"): ap.add_argument(k)
    ap.add_argument("--occasion", choices=("birthday","christmas"), default="birthday")
    ap.add_argument("--fold", choices=("horizontal","vertical"), default="horizontal")
    ap.add_argument("--cover-fit", choices=("auto","contain","crop"), default="auto")
    ap.add_argument("--strict-redraw-check", action="store_true"); ap.add_argument("--allow-draft", action="store_true"); ap.add_argument("--output", required=True)
    a = ap.parse_args(); wd, vert, xm = (Path(a.work_dir) if a.work_dir else None), a.fold == "vertical", a.occasion == "christmas"
    for flag, val in (("--cover",a.cover),("--character",a.character),("--inside",a.inside),("--inside-top",a.inside_top),("--inside-bottom",a.inside_bottom),("--inside-left",a.inside_left),("--inside-right",a.inside_right),("--arch",a.arch),("--cake",a.cake),("--tree",a.tree),("--style-ref",a.style_ref),("--style-json",a.style_json),("--blessing",a.blessing)):
        if val and not os.path.isfile(val): ap.error(f"指定的 {flag} 文件不存在: {val}")
    cov = a.cover or (find1(wd,"cover_vertical_raw","cover_4x3_raw","cover_raw") if vert else find1(wd,"cover_raw","cover_3x4_raw"))
    chr_p = a.character or find1(wd,"character_raw")
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
    tl, wk, pru = (detect_tree_lights(pst) if xm else None), ({"leftPct":44.6,"topPct":7.5} if xm else detect_wick(pst)), uri(pst, 88, 680)

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

    cfg = {"cardId":cid,"occasion":a.occasion,"fold":a.fold,"coverImageUrl":cov_u,"characterImageUrl":chr_u,"insideLeftUrl":ilu,"insideRightUrl":iru,"cakeTableUrl":pru,"archUrl":aru,"linenImageUrl":"","cakeWickPos":wk,"styleTheme":thm,"blessing":bcfg}
    if tl is not None: cfg["treeLights"] = tl
    out_p.parent.mkdir(parents=True, exist_ok=True); out_p.write_text(assemble(cfg), encoding="utf-8")
    print(f"[OK] {'圣诞' if xm else '生日'}立体贺卡（{'4:3上下' if vert else '左右横版'}）-> {out_p} ({out_p.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8"); main()
