"""
手绘 3D 立体弹出式贺卡成品打包器（支持生日 / 圣诞双主题，横版左右折 / 4:3 横向长方形上下折）

通俗用途说明：
无论前面是用宿主 AI 工具（如 Antigravity / 千问多模态）自己重绘的图片，
还是用 ai_redraw.py 调用大模型接口重绘出来的图片，最终都交给本脚本：
1. 把人物、花环拱门、左侧道具（生日木桌蛋糕或圣诞星星灯树）的白底抠干净、清除角落孤立杂点，
   并自动切出 300g 米白水彩卡纸刀模白边；
2. 生日模式自动探测蛋糕顶部蜡烛芯坐标；圣诞模式自动探测圣诞树顶星与树冠 13 颗暖光星灯坐标；
3. 左右横版拟合 3:4 封面与 3:2 展开内页；上下翻折版拟合 4:3 横向长方形封面与 2:3 连续上下内页；
4. 按节日主题内联高清毛边棉麻刺绣底布，将用户祝福语写入配置；
5. 注入防穿模黄金 3D 引擎模板，输出【零外部依赖、双击即开、可微信转发】的独立 .html 文件。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from process_diecut import (  # noqa: E402
    align_arch_feet,
    compute_image_similarity,
    create_die_cut_standee,
    detect_candle_wick_position,
    detect_tree_light_anchors,
    extract_palette_from_cover,
    fit_cover_surface,
    image_to_data_uri,
    split_inside_spread,
    validate_standee_visibility,
)


TEMPLATE_PATH = SKILL_ROOT / "resources" / "card_shell_template.html"
LINEN_BIRTHDAY_CANDIDATES = (
    SKILL_ROOT / "resources" / "embroidery_linen.webp",
    SKILL_ROOT / "resources" / "embroidery_linen.png",
)
LINEN_BLANK_CANDIDATES = (
    SKILL_ROOT / "resources" / "embroidery_linen_blank.webp",
    SKILL_ROOT / "resources" / "embroidery_linen_blank.png",
)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def find_first_existing(base_dir: Optional[Path], *stems: str) -> Optional[str]:
    """在指定工作目录下按给定文件名候选与常见图片后缀依次查找首个存在的文件。"""
    if not base_dir or not base_dir.is_dir():
        return None
    for stem in stems:
        for ext in IMAGE_EXTS:
            candidate = base_dir / f"{stem}{ext}"
            if candidate.is_file():
                return str(candidate)
    return None


def smart_split_sentences(text: str) -> List[str]:
    """
    当用户发来一整段未分行的较长祝福语时，按中文标点温和切分成 3~6 行适合棉麻刺绣排版的短句。
    """
    parts = [s.strip() for s in re.split(r"(?<=[。！？；～!?;])\s*|\n+", text.strip()) if s.strip()]
    if len(parts) == 1 and len(parts[0]) > 20:
        parts = [s.strip() for s in re.split(r"(?<=[，,])\s*", parts[0]) if s.strip()]
    return parts[:7]


def normalize_blessing(raw: Dict[str, Any], occasion: str = "birthday") -> Dict[str, Any]:
    """
    校验并整理祝福语字段，根据生日/圣诞主题填充得体的默认兜底文案，保证刺绣排版匀称美观。
    """
    is_christmas = occasion == "christmas"
    recipient = str(raw.get("recipient") or "亲爱的朋友：").strip()
    if recipient and not recipient.endswith(("：", ":")):
        recipient = recipient + "："

    default_lines = (
        [
            "愿冬夜的每一盏星灯都为你闪亮，",
            "愿雪落之时有热茶与欢喜相伴，",
            "愿来年温柔顺遂，平安常在。",
        ]
        if is_christmas
        else [
            "愿你如期遇见所有温柔，",
            "眼里常怀星辰与热爱，",
            "岁岁欢愉，万事胜意。",
        ]
    )

    lines_val = raw.get("lines")
    if lines_val is None:
        lines = default_lines
    elif isinstance(lines_val, str):
        lines = smart_split_sentences(lines_val) or default_lines
    elif isinstance(lines_val, list):
        collected: List[str] = []
        for item in lines_val:
            s = str(item or "").strip()
            if not s:
                continue
            if len(s) > 26:
                collected.extend(smart_split_sentences(s))
            else:
                collected.append(s)
        lines = collected or default_lines
    else:
        raise ValueError("blessing.lines 字段格式错误：必须是字符串或字符串数组")

    total_chars = sum(len(x) for x in lines)
    if len(lines) > 8 or total_chars > 110:
        print(
            f"[提示] 当前祝福语正文共 {len(lines)} 行 / {total_chars} 字，已启用紧凑刺绣排版并保留前 8 行；"
            f"为获得最佳棉麻布面留白效果，建议精简在 3~7 行、100 字以内。",
            file=sys.stderr,
        )
        lines = lines[:8]

    default_closing = "圣诞快乐，冬日安暖！" if is_christmas else "生日快乐！"
    closing = str(raw.get("closing") or default_closing).strip()
    signature = str(raw.get("signature") or "你的好友").strip()
    sub_signature = str(raw.get("subSignature") or "").strip()

    return {
        "recipient": recipient,
        "lines": lines,
        "closing": closing,
        "signature": signature,
        "subSignature": sub_signature,
    }


def safe_embed_json(data: Dict[str, Any]) -> str:
    """将配置字典序列化并安全转义 <、>、& 与 Unicode 行分隔符，杜绝内联 <script> 被意外截断或注入。"""
    raw = json.dumps(data, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="将重绘图片与定制祝福语打包为独立 3D 立体贺卡 HTML（支持生日/圣诞与横/竖4:3双版式）")
    parser.add_argument("--work-dir", help="包含重绘原图与 blessing.json 的工作目录")
    parser.add_argument("--occasion", choices=("birthday", "christmas"), default="birthday",
                        help="贺卡节日主题：birthday（生日，默认）或 christmas（圣诞）")
    parser.add_argument("--fold", choices=("horizontal", "vertical"), default="horizontal",
                        help="翻折方式：horizontal（左右对折）或 vertical（横向 4:3 长方形上下掀开）")
    parser.add_argument("--cover", help="重绘后的全新封面图路径（横版 3:4，上下版 4:3）")
    parser.add_argument("--character", help="重绘后的白底（或透明底）立体人物图路径")
    parser.add_argument("--inside", help="重绘后的内页底图（左右版 3:2，上下 4:3 版 2:3）")
    parser.add_argument("--inside-top", help="上下翻折版独立上内页图片（4:3）")
    parser.add_argument("--inside-bottom", help="上下翻折版独立下内页图片（4:3）")
    parser.add_argument("--inside-left", help="可选：单独传入左内页图片路径")
    parser.add_argument("--inside-right", help="可选：单独传入右内页图片路径")
    parser.add_argument("--arch", help="可选：重绘后的白底花环拱门图路径")
    parser.add_argument("--cake", help="可选：生日模式白底木桌双层蛋糕图路径")
    parser.add_argument("--tree", help="可选：圣诞模式白底立体圣诞树图路径")
    parser.add_argument("--style-ref", help="可选：原始封面风格参考图路径，用于防贴原图校验")
    parser.add_argument("--style-json", help="可选：style_profile.json 路径")
    parser.add_argument("--blessing", help="可选：blessing.json 路径")
    parser.add_argument("--recipient", help="直接传入收信人称呼（覆盖 JSON）")
    parser.add_argument("--lines-text", help="直接传入换行分隔的正文句子（覆盖 JSON）")
    parser.add_argument("--closing", help="直接传入结尾祝词（覆盖 JSON）")
    parser.add_argument("--signature", help="直接传入落款署名（覆盖 JSON）")
    parser.add_argument("--sub-signature", help="直接传入副署名或日期（覆盖 JSON）")
    parser.add_argument("--save-processed", action="store_true", help="同时将抠图裁边后的 PNG 存一份到 work/processed 方便查看")
    parser.add_argument("--strict-redraw-check", action="store_true", help="严格检查模式：若封面与参考原图高度雷同则拒绝打包")
    parser.add_argument("--output", required=True, help="最终输出的单文件 HTML 路径")

    args = parser.parse_args()
    work_dir = Path(args.work_dir) if args.work_dir else None
    vertical = args.fold == "vertical"
    is_christmas = args.occasion == "christmas"

    cover_path = args.cover or (
        find_first_existing(work_dir, "cover_vertical_raw", "cover_4x3_raw", "cover_raw")
        if vertical
        else find_first_existing(work_dir, "cover_raw", "cover_3x4_raw")
    )
    char_path = args.character or find_first_existing(work_dir, "character_raw")
    inside_path = args.inside or (
        find_first_existing(work_dir, "inside_vertical_raw", "inside_2x3_raw")
        if vertical
        else find_first_existing(work_dir, "inside_raw")
    )
    top_path = args.inside_top or (find_first_existing(work_dir, "inside_top") if vertical else None)
    bottom_path = args.inside_bottom or (find_first_existing(work_dir, "inside_bottom") if vertical else None)
    if vertical and (top_path or bottom_path):
        if not all(path and os.path.isfile(path) for path in (top_path, bottom_path)):
            parser.error("上下翻折版需要同时提供可读的上内页和下内页")
    elif vertical and not (inside_path and os.path.isfile(inside_path)):
        parser.error("上下翻折版需要 --inside（2:3 连续底图）或完整的 --inside-top 与 --inside-bottom")

    inside_left_path = args.inside_left or find_first_existing(work_dir, "inside_left")
    inside_right_path = args.inside_right or find_first_existing(work_dir, "inside_right")
    arch_path = args.arch or find_first_existing(work_dir, "arch_raw", "christmas_arch_raw")
    if is_christmas:
        if args.cake:
            parser.error("圣诞模式禁止使用生日蛋糕素材 --cake，请提供立体圣诞树 --tree 或工作目录下的 tree_raw.png")
        left_prop_path = args.tree or find_first_existing(work_dir, "tree_raw", "christmas_tree_raw")
        if not left_prop_path or not os.path.isfile(left_prop_path):
            parser.error("圣诞模式必须提供立体圣诞树素材 --tree（或在 --work-dir 中放置 tree_raw.png）")
    else:
        if args.tree:
            parser.error("生日模式请使用双层蛋糕素材 --cake 或 cake_raw.png；若要制作圣诞贺卡请加上 --occasion christmas")
        left_prop_path = args.cake or find_first_existing(work_dir, "cake_raw")
        if not left_prop_path or not os.path.isfile(left_prop_path):
            parser.error("生日模式必须提供蛋糕桌椅素材 --cake（或在 --work-dir 中放置 cake_raw.png）")
    style_ref_path = args.style_ref or find_first_existing(work_dir, "style_ref")

    if not cover_path or not os.path.isfile(cover_path):
        parser.error("必须提供重绘后的封面图 --cover（或在 --work-dir 中放置 cover_raw.png）")
    if not char_path or not os.path.isfile(char_path):
        parser.error("必须提供重绘后的人物图 --character（或在 --work-dir 中放置 character_raw.png）")
    if args.strict_redraw_check and not (style_ref_path and os.path.isfile(style_ref_path)):
        parser.error("--strict-redraw-check 需要可读取的参考封面图 --style-ref")

    if style_ref_path and os.path.isfile(style_ref_path):
        sim = compute_image_similarity(cover_path, style_ref_path)
        if sim >= 0.96:
            msg = f"[警告] 检测到生成的封面与参考原图视觉相似度高达 {sim*100:.1f}%，疑似直接贴用了原图而非按风格全新重绘！"
            if args.strict_redraw_check:
                raise SystemExit(f"{msg} 已拦截打包（--strict-redraw-check）。")
            print(msg, file=sys.stderr)

    processed_dir = (work_dir / "processed") if (args.save_processed and work_dir) else None
    if processed_dir:
        processed_dir.mkdir(parents=True, exist_ok=True)

    cover_size = (1000, 750) if vertical else (750, 1000)
    print(f"[1/5] 正在适配 {'4:3 横向长方形' if vertical else '3:4 竖版'}封面并分析全卡统一色盘...")
    cover_img = fit_cover_surface(cover_path, size=cover_size)
    cover_uri = image_to_data_uri(cover_img, fmt="WEBP", quality=88)

    style_theme = extract_palette_from_cover(cover_img)
    style_json_path = args.style_json or (str(work_dir / "style_profile.json") if work_dir and (work_dir / "style_profile.json").is_file() else None)
    if style_json_path and os.path.isfile(style_json_path):
        try:
            with open(style_json_path, "r", encoding="utf-8") as f:
                sp = json.load(f)
            if isinstance(sp.get("styleTheme"), dict):
                style_theme.update({k: v for k, v in sp["styleTheme"].items() if v})
        except Exception as err:
            print(f"[提示] 读取 style_profile.json 失败，已使用封面图像提取配色: {err}")

    print("[2/5] 正在为中央人物立牌执行去杂点抠图并生成 300g 米白刀模卡纸边...")
    char_out = str(processed_dir / "character_standee.png") if processed_dir else None
    char_standee = create_die_cut_standee(char_path, out_path=char_out, border_px=13, target_max_size=820, allow_inner_hole=False)
    char_ok, char_ratio = validate_standee_visibility(char_standee)
    if not char_ok:
        raise SystemExit(
            f"错误：检测到中央人物图片 '{char_path}' 有效主体过少或为纯白/全透明空白图（可见占比 {char_ratio*100:.2f}%），"
            f"已拦截打包，请检查或重新生成带纯白背景的人物插画。"
        )
    char_uri = image_to_data_uri(char_standee, fmt="WEBP", quality=88, max_dim=760)

    print("[3/5] 正在切分展开内页并内联对应节日毛边棉麻刺绣底布...")
    inside_left_uri = ""
    inside_right_uri = ""
    if vertical and top_path and bottom_path:
        top = fit_cover_surface(top_path, size=(1000, 750))
        bottom = fit_cover_surface(bottom_path, size=(1000, 750))
        inside_left_uri = image_to_data_uri(top, fmt="WEBP", quality=86)
        inside_right_uri = image_to_data_uri(bottom, fmt="WEBP", quality=86)
    elif not vertical and inside_left_path and os.path.isfile(inside_left_path) and inside_right_path and os.path.isfile(inside_right_path):
        l_img = fit_cover_surface(inside_left_path, size=(700, 934))
        r_img = fit_cover_surface(inside_right_path, size=(700, 934))
        inside_left_uri = image_to_data_uri(l_img, fmt="WEBP", quality=86)
        inside_right_uri = image_to_data_uri(r_img, fmt="WEBP", quality=86)
    elif inside_path and os.path.isfile(inside_path):
        spread_size = (1000, 1500) if vertical else (1400, 934)
        l_img, r_img = split_inside_spread(inside_path, size=spread_size, vertical=vertical)
        inside_left_uri = image_to_data_uri(l_img, fmt="WEBP", quality=86)
        inside_right_uri = image_to_data_uri(r_img, fmt="WEBP", quality=86)

    linen_uri = ""
    linen_candidates = LINEN_BLANK_CANDIDATES if is_christmas else LINEN_BIRTHDAY_CANDIDATES
    chosen_linen = next((p for p in linen_candidates if p.is_file()), None)
    if chosen_linen is not None:
        linen_img = Image.open(chosen_linen)
        linen_uri = image_to_data_uri(linen_img, fmt="WEBP", quality=86, max_dim=680)
    else:
        print(
            f"[提示] 未找到{'圣诞空白' if is_christmas else '生日'}棉麻刺绣底布 '{linen_candidates[0].name}'，"
            f"已使用主题隔离的纯矢量 CSS 棉麻刺绣底板（绝不跨主题混用底布）。",
            file=sys.stderr,
        )

    prop_label = "立体圣诞树并定位闪烁星灯" if is_christmas else "左前木桌蛋糕并定位蜡烛芯"
    print(f"[4/5] 正在裁切后景拱门与{prop_label}...")
    arch_uri = ""
    if arch_path and os.path.isfile(arch_path):
        arch_out = str(processed_dir / "arch_standee.png") if processed_dir else None
        arch_standee = create_die_cut_standee(arch_path, border_px=10, target_max_size=920, allow_inner_hole=True)
        if vertical:
            arch_standee = align_arch_feet(arch_standee)
        arch_ok, arch_ratio = validate_standee_visibility(arch_standee)
        if not arch_ok:
            raise SystemExit(
                f"错误：检测到花环拱门图片 '{arch_path}' 为空白、全透明或主体不可见（可见占比 {arch_ratio*100:.2f}%），已拦截打包。"
            )
        if arch_out:
            arch_standee.save(arch_out)
        arch_uri = image_to_data_uri(arch_standee, fmt="WEBP", quality=86, max_dim=880)

    cake_uri = ""
    cake_wick_pos = {"leftPct": 44.6, "topPct": 7.5}
    tree_lights = None
    if left_prop_path and os.path.isfile(left_prop_path):
        prop_filename = "tree_standee.png" if is_christmas else "cake_standee.png"
        prop_out = str(processed_dir / prop_filename) if processed_dir else None
        prop_standee = create_die_cut_standee(left_prop_path, out_path=prop_out, border_px=11, target_max_size=760, allow_inner_hole=False)
        prop_ok, prop_ratio = validate_standee_visibility(prop_standee)
        if not prop_ok:
            prop_cn = "立体圣诞树" if is_christmas else "蛋糕桌椅"
            raise SystemExit(
                f"错误：检测到{prop_cn}图片 '{left_prop_path}' 为空白、全透明或主体不可见（可见占比 {prop_ratio*100:.2f}%），已拦截打包。"
            )
        if is_christmas:
            tree_lights = detect_tree_light_anchors(prop_standee)
            if len(tree_lights.get("lights", [])) < 3:
                print(
                    "[提示] 当前圣诞树树冠可挂星灯的实心枝干区域较窄，已自动按实心边界收敛星灯数量以确保 0 悬空。",
                    file=sys.stderr,
                )
        else:
            cake_wick_pos = detect_candle_wick_position(prop_standee)
        cake_uri = image_to_data_uri(prop_standee, fmt="WEBP", quality=88, max_dim=680)

    raw_blessing: Dict[str, Any] = {}
    blessing_path = args.blessing or (str(work_dir / "blessing.json") if work_dir and (work_dir / "blessing.json").is_file() else None)
    if blessing_path and os.path.isfile(blessing_path):
        with open(blessing_path, "r", encoding="utf-8") as f:
            loaded_blessing = json.load(f)
        if not isinstance(loaded_blessing, dict):
            raise SystemExit("错误：blessing.json 顶层必须是 JSON 对象（{...}），不能是数组或纯文本。")
        raw_blessing = loaded_blessing

    if args.recipient is not None:
        raw_blessing["recipient"] = args.recipient
    if args.lines_text is not None:
        raw_blessing["lines"] = args.lines_text.replace("\\n", "\n")
    if args.closing is not None:
        raw_blessing["closing"] = args.closing
    if args.signature is not None:
        raw_blessing["signature"] = args.signature
    if args.sub_signature is not None:
        raw_blessing["subSignature"] = args.sub_signature

    try:
        blessing_cfg = normalize_blessing(raw_blessing, occasion=args.occasion)
    except ValueError as err:
        raise SystemExit(f"错误：祝福语数据格式无效：{err}")

    id_seed = "|".join([
        args.occasion,
        args.fold,
        Path(args.output).name,
        cover_uri[:256],
        char_uri[:256],
        json.dumps(blessing_cfg, ensure_ascii=False, sort_keys=True),
    ])
    card_id = hashlib.sha256(id_seed.encode("utf-8")).hexdigest()[:12]

    card_config: Dict[str, Any] = {
        "cardId": card_id,
        "occasion": args.occasion,
        "fold": args.fold,
        "coverImageUrl": cover_uri,
        "characterImageUrl": char_uri,
        "insideLeftUrl": inside_left_uri,
        "insideRightUrl": inside_right_uri,
        "cakeTableUrl": cake_uri,
        "archUrl": arch_uri,
        "linenImageUrl": linen_uri,
        "cakeWickPos": cake_wick_pos,
        "styleTheme": style_theme,
        "blessing": blessing_cfg,
    }
    if tree_lights is not None:
        card_config["treeLights"] = tree_lights

    print("[5/5] 正在注入防穿模 3D 贺卡引擎并生成单文件 HTML 成品...")
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"找不到模板文件: {TEMPLATE_PATH}")

    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    config_json = safe_embed_json(card_config)
    pattern = re.compile(r"/\*__CARD_CONFIG_START__\*/[\s\S]*?/\*__CARD_CONFIG_END__\*/")
    if not pattern.search(template_html):
        raise RuntimeError("模板中未找到 /*__CARD_CONFIG_START__*/ 注入标记")

    final_html = pattern.sub(
        lambda _: f"/*__CARD_CONFIG_START__*/{config_json}/*__CARD_CONFIG_END__*/",
        template_html,
        count=1,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024.0
    theme_cn = "圣诞贺卡" if is_christmas else "生日贺卡"
    fold_cn = "4:3 上下翻折版" if vertical else "左右对折横版"
    print(f"[OK] 独立 3D {theme_cn}（{fold_cn}）HTML 生成成功！")
    print(f"     输出文件: {out_path.resolve()} ({size_kb:.1f} KB)")
    if is_christmas:
        cnt = len((tree_lights or {}).get("lights", []))
        print(f"     风格主题: {style_theme.get('styleName')} | 圣诞树星灯: 顶星 + {cnt} 颗树冠星灯")
    else:
        print(f"     风格主题: {style_theme.get('styleName')} | 蜡烛芯坐标: {cake_wick_pos}")
    print(f"     收信人  : {blessing_cfg['recipient']} | 署名: {blessing_cfg['signature']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
