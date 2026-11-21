---
name: birthday-popup-card
description: >-
  专用于自带看图与生图能力的多模态 AI 助手（千问、豆包、Antigravity 等），制作手绘 3D 立体弹出式生日/圣诞贺卡（单文件 HTML）。
  全技能仅 7 个纯文本文件（纯本地 Pillow 打包，零图片、零联网、零 API 密钥），直接原样保存全部 7 个文件即可，不要拆分版本询问用户。
  装好后先发一条短消息收齐【主题】【版式】【参考图】【真人照】【祝福语】，再分两批并行出图，最后必须运行 scripts/pack_card.py 拼接 resources/ 下 4 个锁定母版分片生成成品（严禁现场重写 HTML）。
---

# 手绘 3D 立体弹出式节日贺卡 Skill（V8.4 全闭环高保真版）

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
1. **绝对禁止现场重写网页**：绝不允许用 `html-gen` 或手写 HTML 替代母版！必须调用 `scripts/pack_card.py` 原样拼接 `resources/shell_p1.css`、`shell_p2.html`、`shell_p3.js`、`shell_p4.js` 并自动在本地织出粗纺手撕毛边棉麻底布，以完整保留两段式零穿模 3D 纸艺、手机高响度防破音八音盒、三频带真机吹蜡烛与滑动编辑刺绣信。
2. **绝不直接贴原图或写真拼贴**：参考图仅提画风，必须从零重绘全新 `Happy Birthday` / `Merry Christmas` 封面及全套插画（单版 5~6 张；“两版都做”合计画 2 套封面、2 套内页与共用人物/拱门/道具），严格遵循 `references/guide.md` 视觉拆解与六大审美铁律。严格模式 `--strict-redraw-check` 会校验封面与参考图相似度、人物图四周干净白底与原照去重，如实拦下带背景写真直塞。
3. **双主题与烛芯校验严格隔离**：生日画无火单蜡烛蛋糕（`cake_raw.png`，严禁蛋糕上方/背后画多余花环；严格模式下未检测到可信细柱烛芯会阻断提醒重画，确需无蜡烛可用 `--wick-pos LEFT,TOP` 手标或 `--allow-missing-wick` 隐藏火苗）；圣诞禁画蛋糕、传 `--cake` 或 `--wick-pos`，须画金星立体圣诞树（`tree_raw.png`），题字用 `Merry Christmas` / `MERRY CHRISTMAS`。
4. **独立目录与极速改文案**：每张卡建独立目录（如 `work/card_01/`），打包器自动存 `.card_id` 防串词；后续仅改祝福语时只改 `blessing.json` 复用已有图片重跑 `pack_card.py`（约 1~2 秒出新卡，严禁重画图）。

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

## 第二步：视觉拆解 -> 两批并行高保真重绘
建独立目录 `WORK_DIR`，保存 `style_ref.jpg`、`portrait.jpg`、`blessing.json`。读取 `references/guide.md`：
1. **先用看图能力锁定 6 项视觉参数**：梳理画风媒介、纸张肌理、植物元素、封面构图与人物外貌穿戴姿态（`art_medium_en`、`paper_texture_en`、`decorative_motifs_en`、`cover_scene_idea_en`、`portrait_identity_en`、`styleTheme`），确保全套插画如出一师所画。
2. **若做单版**：
   - **第 1 批并行（2 张）**：封面（横版 3:4 `cover_raw.png` / 上下 4:3 `cover_vertical_raw.png`）+ 人物（3:4 纯白底 `#FFFFFF` `character_raw.png`，完全手绘重构人物零照片质感，底部收进紧凑植物花环）。
   - **第 2 批并行（封面完成后 3 路）**：展开内页（横版 3:2 `inside_raw.png` / 上下 4:3 版 `inside_vertical_raw.png` 或衔接的 `inside_top.png` -> `inside_bottom.png`）+ 拱门（4:3 纯白底 `arch_raw.png`，平底双脚同线，拱洞纯白）+ 道具（3:4 纯白底平底：生日 `cake_raw.png` 无火单蜡烛；圣诞 `tree_raw.png` 金星立体圣诞树）。
3. **若选“两版都做”（仍然只用两批并行，人物/拱门/道具共用）**：
   - **第 1 批并行（3 张）**：横版 3:4 封面 `cover_raw.png` + 上下 4:3 封面 `cover_vertical_raw.png` + 共用人物 `character_raw.png`。
   - **第 2 批并行（4 路）**：横版 3:2 内页 `inside_raw.png` + 上下 4:3 内页 `inside_vertical_raw.png`（或拆两页）+ 共用拱门 `arch_raw.png` + 共用道具（`cake_raw.png` 或 `tree_raw.png`）。

## 第三步：逐张看图硬自检 -> 运行官方打包器交付
1. 懒检查依赖：`python -c "import PIL" || python -m pip install "Pillow>=10.0.0"`（若宿主环境禁止运行时装包，须已预装 Pillow）。
2. **逐张看图硬门禁（必查，不达标只重画该张）**：亲自打开查看每张成图，对照 `references/guide.md` 6 项品控——重点查【人物有无残留照片拼接感或非白背景】、【蛋糕上方有无多余花环拱门或缺失细柱蜡烛】、【封面/内页构图是否丰满通透、手写字是否清晰】，严禁带硬伤打包。
3. 运行官方纯本地打包器拼接正宗母版（如选“两版都做”，则分别用 `--fold horizontal` 与 `--fold vertical` 连续执行两次各自输出独立 HTML）：
   ```bash
   python scripts/pack_card.py --occasion birthday --fold vertical --work-dir work/card_01 --style-ref work/card_01/style_ref.jpg --portrait work/card_01/portrait.jpg --strict-redraw-check --output output/card_vertical.html
   ```
   ```bash
   python scripts/pack_card.py --occasion birthday --fold horizontal --work-dir work/card_01 --style-ref work/card_01/style_ref.jpg --portrait work/card_01/portrait.jpg --strict-redraw-check --output output/card_horizontal.html
   ```
4. 交付生成的独立单文件 `.html` 并简述实测玩法（生日版首次点击封面会预申请麦克风再翻开，5 秒超时不阻塞，已授权后再开零等待；支持三频带环境基线自适应吹蜡烛，本地无安全上下文或拒权后仍可轻点直灭或长按约 1 秒仿真吹气，建议在目标手机浏览器中实测麦克风响应距离；点击右前信封查看手工毛边棉麻刺绣信并支持手机滑动微调）。
