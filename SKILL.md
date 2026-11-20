---
name: birthday-popup-card
description: >-
  专用于自带看图与生图能力的多模态 AI 助手（千问、豆包、Antigravity 等），制作手绘 3D 立体弹出式生日/圣诞贺卡（单文件 HTML）。
  全技能仅 7 个纯文本文件（纯本地 Pillow 打包，零图片、零联网、零 API 密钥），直接原样保存全部 7 个文件即可，不要拆分版本询问用户。
  装好后先发一条短消息收齐【主题】【版式】【参考图】【真人照】【祝福语】，再分两批并行出图，最后必须运行 scripts/pack_card.py 拼接 resources/ 下 4 个锁定母版分片生成成品（严禁现场重写 HTML）。
---

# 手绘 3D 立体弹出式节日贺卡 Skill（V8.1 云端直装保真版）

## 安装铁律（仅 7 个纯文本文件，零图片、零联网、零密钥）
1. `SKILL.md`
2. `references/guide.md`
3. `scripts/pack_card.py`
4. `resources/shell_p1.css`
5. `resources/shell_p2.html`
6. `resources/shell_p3.js`
7. `resources/shell_p4.js`

- **直接完整装入上述 7 个文件**：本技能无任何外接 API 或双路线选择，**严禁弹窗让用户选“完整版/轻量版/API 版”，严禁自行重写脚本，严禁丢弃或跳过 `resources/` 下 4 个母版分片**。

## 4 条不可逾越红线
1. **绝对禁止现场重写网页**：绝不允许用 `html-gen` 或手写 HTML 替代母版！必须调用 `scripts/pack_card.py` 原样拼接 `resources/shell_p1.css`、`shell_p2.html`、`shell_p3.js`、`shell_p4.js`，以 100% 保证两段式零穿模 3D 纸艺、手机高响度防破音八音盒、翻开前预授权吹蜡烛、手工毛边棉麻刺绣信与手机滑动编辑效果。
2. **绝不直接贴原图**：参考图仅提画风，必须从零重绘全新 `Happy Birthday` / `Merry Christmas` 封面及全套插画（单页内页 5 张，上下拆画 6 张），遵循 `references/guide.md` 六大审美铁律。
3. **双主题严格隔离**：生日画无火单蜡烛蛋糕（`cake_raw.png`）；圣诞禁画蛋糕或传 `--cake`，须画金星立体圣诞树（`tree_raw.png`），题字用 `Merry Christmas` / `MERRY CHRISTMAS`。
4. **独立目录与极速改文案**：每张卡建独立目录（如 `work/card_01/`），打包器自动存 `.card_id` 防串词；后续仅改祝福语时只改 `blessing.json` 复用已有图片重跑 `pack_card.py`（1~2 秒出新卡，严禁重画图）。

## 第一步：装完秒进对话（先收素材，不阻塞装依赖）
装完直接发下面这条短消息（用户已提供的内容直接复用，只问缺项）：

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

## 第二步：两批并行重绘全套插画
建独立目录 `WORK_DIR`，保存 `style_ref.jpg`、`portrait.jpg`、`blessing.json`。读取 `references/guide.md`，用宿主内置看图与生图能力分两批并行出图：
1. **第 1 批并行（2 张）**：封面（横版 3:4 `cover_raw.png` / 上下 4:3 `cover_vertical_raw.png`）+ 人物（3:4 纯白底 `#FFFFFF` `character_raw.png`，底部收进植物花环）。
2. **第 2 批并行（封面完成后同时起跑 3 路）**：展开内页（横版 3:2 `inside_raw.png` / 上下 4:3 版 `inside_vertical_raw.png` 或衔接的 `inside_top.png` -> `inside_bottom.png`）+ 拱门（4:3 纯白底 `arch_raw.png`，平底双脚同线，拱洞纯白）+ 道具（3:4 纯白底平底：生日 `cake_raw.png` 无火单蜡烛，圣诞 `tree_raw.png` 立体圣诞树）。

## 第三步：审美自检 -> 运行官方打包器交付
1. 懒检查依赖：`python -c "import PIL" || python -m pip install "Pillow>=10.0.0"`（若云端沙箱禁止运行时装包，则需宿主环境已预装 Pillow）
2. 对照 `references/guide.md` 核对全套图（5~6 张，上下拆页查折线接缝），单张不达标只重画该张。
3. 运行官方唯一纯本地打包器拼接正宗母版：
   ```bash
   python scripts/pack_card.py --occasion birthday --fold vertical --work-dir work/card_01 --style-ref work/card_01/style_ref.jpg --strict-redraw-check --output output/card.html
   ```
4. 交付生成的独立单文件 `.html` 并简述玩法（生日版首次点封面先预授权麦克风再翻开，已授权后再开零等待；HTTPS 可吹灭蜡烛，本地附件或拒权走轻点/长按约 1 秒兜底；点右前信封看棉麻刺绣信并支持手机滑动微调文字）。
