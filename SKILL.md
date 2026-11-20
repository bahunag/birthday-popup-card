---
name: birthday-popup-card
description: >-
  当用户通过 GitHub 链接要求配置“立体贺卡 Skill”或“立体生日贺卡 Skill”，或要求制作手绘 3D 立体弹出式生日/圣诞贺卡（HTML）时激活。
  配置好后必须先用一条简短消息快速确认【主题（生日／圣诞）】【版式（上下翻折 4:3 横向长方形／左右横版／两版都做）】，并收集【封面风格参考图（横竖不限）】【人物真人照】【祝福语（模板填空或自己写二选一）】；用户已提供的内容直接复用，不要在首次回复前卡在环境检查。
  收齐后按两批并行重绘全套同画风插画，并通过 scripts/build_card.py 打包为两段式零穿模单文件 HTML（支持高响度手机八音盒、翻开前预授权吹蜡烛、圣诞常亮闪烁星星灯树与可滑动编辑棉麻刺绣信）。
---

# 手绘 3D 立体弹出式节日贺卡 Skill（生日 / 圣诞双主题 · V6 极速定稿版）

## 不可逾越的 4 条红线
1. **绝不直接贴参考原图或生活照**：参考图仅用于提取画风，必须从零重绘全新的 `Happy Birthday`（生日）或 `Merry Christmas`（圣诞）封面及全套 5 张插画；画面严格遵循 [references/aesthetic_guidelines.md](./references/aesthetic_guidelines.md)（纸本哑光、60-30-10 配色、留白呼吸感、禁止塑料 3D 光感与荧光色）。
2. **双主题严格隔离**：生日画无火焰单蜡烛双层蛋糕（`cake_raw.png`）；圣诞**禁止画蛋糕或传 `--cake`**，必须画立体圣诞树（`tree_raw.png`），封面与拱门写 `Merry Christmas` / `MERRY CHRISTMAS`，刺绣信仅用 `embroidery_linen_blank.webp`。
3. **锁定极简外壳与零 Emoji**：严禁擅改 `resources/card_shell_template.html` 的两段式零穿模引擎、手机 50% 音量高响度八音盒、翻开前预授权逻辑与可滑动编辑弹窗；全页零 Emoji。
4. **独立工作目录与极速返工**：每张卡使用独立目录（如 `work/xmas_v43_01/`）防串图；若用户后续**只改祝福语**，直接更新 `blessing.json` 复用已有图片重跑 `build_card.py`（1~2 秒出新卡，严禁重画图）。

---

## 第一步：配置完秒进对话（先收素材，后查环境）
- 完成技能安装后，**不要先跑 `pip install` 或 `--check-env`**，直接发下面这段短消息（用户已经给过的项直接复用，只追问缺项）：

```text
配置好了。请确认主题、版式，并发送素材：

1. 节日主题：生日贺卡 ／ 圣诞贺卡
2. 贺卡版式：上下翻折（4:3 横向长方形） ／ 左右横版 ／ 两版都做
3. 封面风格参考图：横竖不限，仅参考画风
4. 中央人物照：正面或半身真人照
5. 祝福语（二选一）：
   - 选项一（用现成模板）：发【抬头称呼】、【落款署名】、【日期（选填）】及想补充的 1~2 句心里话（选填）
   - 选项二（自己写）：直接发完整祝福语
```

> 模板正文与断行规范见 [references/blessing_template.md](./references/blessing_template.md)（用户选选项一时按需读取）。

---

## 第二步：两批并行重绘全套插画（提速近一倍，不降画质）
建立独立目录 `WORK_DIR`，保存 `style_ref.jpg`、`portrait.jpg`、`blessing.json`。按自身能力二选一：

### 路径 A：自带看图与生图工具的多模态 Agent（推荐，直接跳过密钥检查）
按需查阅 [references/style_extraction_and_prompts.md](./references/style_extraction_and_prompts.md) 与 [references/aesthetic_guidelines.md](./references/aesthetic_guidelines.md)，**分两批并行出图**：
1. **第 1 批并行（同时画 2 张，只依赖原参考图）**：
   - 封面：`cover_raw.png`（左右版 3:4）或 `cover_vertical_raw.png`（上下版 **4:3 横向长方形**）
   - 中央人物：`character_raw.png`（3:4 纯白底 `#FFFFFF`，底部收进同款花环底座）
2. **第 2 批并行（封面完成后同时起跑 3 路）**：
   - 展开内页：左右版 `inside_raw.png`（3:2）；上下 4:3 版 `inside_vertical_raw.png`（2:3）或先后衔接的 `inside_top.png` -> `inside_bottom.png`（各 4:3）
   - 后景拱门：`arch_raw.png`（4:3 纯白底 `#FFFFFF`，平底双脚同线，拱洞纯白）
   - 左前道具（3:4 纯白底 `#FFFFFF` 平底）：生日画 `cake_raw.png`（无火单蜡烛），圣诞画 `tree_raw.png`（立体圣诞树，顶金星）

### 路径 B：纯命令行代码型 Agent（无内置生图工具）
1. 先检查环境：`python scripts/ai_redraw.py --check-env`（未配密钥时引导用户通过 `.env.example` 安全写入本机 `.env`，严禁聊天发明文密钥）。
2. 运行脚本（脚本已内置两批并行调度与 429 自动重试）：
   ```bash
   python scripts/ai_redraw.py --occasion birthday --fold vertical --style-ref work/c1/style_ref.jpg --portrait work/c1/portrait.jpg --out-dir work/c1
   ```

---

## 第三步：懒查依赖 -> 审美自检 -> 一键打包交付
1. **懒加载检查依赖**（已有 Pillow 直接跳过安装）：
   ```bash
   python -c "import PIL" || pip install -r requirements.txt
   ```
2. 对照 [references/aesthetic_guidelines.md](./references/aesthetic_guidelines.md) 快速确认五图画风统一、白底干净、零穿帮（单张不达标只重画该张）。
3. **运行 `scripts/build_card.py` 打包**（按主题改 `--occasion birthday|christmas`，按版式改 `--fold horizontal|vertical`）：
   ```bash
   python scripts/build_card.py --occasion christmas --fold vertical --work-dir work/c1 --style-ref work/c1/style_ref.jpg --strict-redraw-check --output output/card.html
   ```
4. 交付成品路径与简洁玩法（提醒用户：生日版点封面会先完成麦克风预授权再翻开，在 HTTPS 网页链接可直接对着手机吹灭，本地附件或拒权自动无缝走轻点/长按约 1 秒兜底；点击右前火漆信封展开刺绣信并支持手机上下滑动微调文字）。
