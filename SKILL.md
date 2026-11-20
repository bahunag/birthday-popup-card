---
name: birthday-popup-card
description: >-
  当用户通过 GitHub 链接要求配置“立体贺卡 Skill”或“立体生日贺卡 Skill”，或要求制作手绘 3D 立体弹出式生日/圣诞贺卡（HTML）时激活。
  Agent 配置好后必须先主动向用户确认【主题（生日／圣诞）】【版式（上下翻折 4:3 横向长方形／左右横版／两版都做）】，并收集【1. 贺卡封面风格参考图（横竖不限）】【2. 中央人物真人照片】【3. 祝福语（选项一：套用生日/圣诞现成模板，只需填写抬头、落款及可选补充句子；选项二：自己写完整祝福语）】。
  收齐后，根据参考图识别绘画风格与配色，重新绘制全新的节日封面、同画风立体人物、展开内页、花环拱门与节日道具（生日画无火焰双层蛋糕，圣诞画挂满星星灯的立体圣诞树），
  再通过 scripts/process_diecut.py 与 scripts/build_card.py 自动抠图加 300g 米白卡纸白边并打包为防穿模单文件 HTML（带八音盒、生日吹蜡烛自动请求高灵敏麦克风+长按兜底、圣诞常亮闪烁星星灯与棉麻刺绣信）。
---

# 手绘 3D 立体弹出式节日贺卡生成 Skill（生日 / 圣诞双主题）

本技能包用于制作**左右翻折横版**或**上下翻折 4:3 横向长方形矩形贺卡**，支持**生日**与**圣诞**双主题切换，具备 4 层零穿模 3D 纸艺安全走廊、300g 米白卡纸刀模白边、Web Audio 机械八音盒、生日吹蜡烛（翻开自动请求高灵敏度手机麦克风 + 非 HTTPS 零报错轻点/长按兜底）、圣诞常亮闪烁星星灯树以及毛边棉麻刺绣祝福信的**独立单文件 HTML 立体贺卡**。

---

## 铁律红线（绝对禁止违反）

1. **严禁直接把参考封面贴上去**：用户给的封面图只是“画风和审美参考”（横图竖图都不影响）。必须提取它的画笔媒介、配色与主题元素，**从零重新绘制一张全新的 `Happy Birthday`（生日）或 `Merry Christmas`（圣诞）贺卡封面**（原图相似度不得雷同）。
2. **严禁直接贴未经重绘的生活照片或用简陋图形糊弄**：必须按封面的统一画风重绘出纯白底半身人物立牌、展开内页底图、花环拱门与左前立体道具：
   - **生日模式（`--occasion birthday`）**：左前绘制木桌椅与双层蛋糕（顶部正中插唯一未点燃蜡烛，**严禁提前画火焰**，由网页引擎动态燃烧与吹灭）。
   - **圣诞模式（`--occasion christmas`）**：**不要画蛋糕！** 左前改为绘制同画风立体手绘圣诞树（挂彩球、松果、丝带与树顶金星，网页引擎自动在树顶与树冠点亮常亮闪烁的暖光星星灯）；封面与拱门文字全部改为 `Merry Christmas` / `MERRY CHRISTMAS`；全程零“生日”穿帮文字。
3. **严禁使用 Emoji 表情包做图标，严禁破坏防穿模引擎**：不要擅自修改 `resources/card_shell_template.html` 中的 4 层零穿模安全走廊、Apple 极简纯线条 SVG 图标、单行无滚动条底部胶囊栏及声学互动算法；务必通过 `scripts/build_card.py` 完成确定性打包。

---

## 第一步：确认配置并收集素材（含双节日祝福语二选一）

配置完成且素材、主题或版式尚未齐全时，先向用户发送下面这段清晰简洁的引导（只追问尚未提供的项；如果已经给齐主题、版式与三项素材，直接进入第二步）：

```text
配置好了。请确认主题、版式，并发送素材：

1. 节日主题：生日贺卡 ／ 圣诞贺卡
2. 贺卡版式：上下翻折（4:3 横向长方形） ／ 左右横版 ／ 两版都做
3. 封面风格参考图：任意喜欢的插画或贺卡封面（横图、竖图都不影响，仅参考画风）
4. 中央人物照片：正面或半身真人照
5. 祝福语（二选一）：
   - 选项一（用现成模板）：只需告诉我【抬头称呼】、【落款署名】、【日期/副署名（选填）】，以及想额外补充的 1~2 句灵活心里话（选填）
   - 选项二（自己写）：直接发来或上传您想写的完整祝福语
```

> 完整的生日模板与圣诞模板正文请查阅 [references/blessing_template.md](./references/blessing_template.md)。如果用户选择“选项一”，Agent 需按用户所选节日套用对应模板，把用户提交的抬头、落款及可选补充句自然融合成 `work/blessing.json`。

---

## 第二步：画风识别与全套视觉重绘（按自身能力自动分流）

素材齐全且确定了主题（`birthday` / `christmas`）和版式（`horizontal` / `vertical` / `both`）后，建立工作目录 `work/`（保存参考封面 `work/style_ref.jpg`、真人照 `work/portrait.jpg`、祝福语 `work/blessing.json`）。

### 路径 A：当前宿主 Agent 自带“看图 + 画图/编图”工具（推荐，无需额外配 Key）

1. **提取画风 DNA**：阅读 [references/style_extraction_and_prompts.md](./references/style_extraction_and_prompts.md)，观察用户的参考封面图（无论横竖）与真人照，写出 `work/style_profile.json`（示例见 [examples/sample_style_profile.json](./examples/sample_style_profile.json)）。
2. **按所选主题与版式生成全新图片**：
   - **左右横版封面** `work/cover_raw.png`（`3:4` 竖版）：生日写 `Happy Birthday`，圣诞写 `Merry Christmas`。
   - **上下翻折版封面** `work/cover_vertical_raw.png`（**`4:3` 横向长方形**，与横版风格完全一致）：生日写 `Happy Birthday`，圣诞写 `Merry Christmas`。如果用户选“两版都做”，分别画出 3:4 与 4:3 两张同画风封面。
   - **中央立体人物** `work/character_raw.png`（`3:4` 竖版，**纯白底 `#FFFFFF`**，四周留干净白边且无孤立杂点）：按封面画风重绘真人，底端收进同款植物花环底座（圣诞可点缀冬青红果、雪松与暖围巾感）。
   - **展开内页**：
     - 左右横版：`work/inside_raw.png`（`3:2` 横幅，边缘丰富植物装饰，中部大面积低对比淡彩远景与小径）。
     - 上下翻折 4:3 版：`work/inside_vertical_raw.png`（**`2:3` 宽敞竖向连续画面**，上半页 `4:3` + 下半页 `4:3` 横向中线折痕自然衔接，两侧与上下沿布置浓色植物，中部低对比远景与小径留白）；也可分别生成 `work/inside_top.png` 与 `work/inside_bottom.png`（各 `4:3`）。
   - **后景立体拱门** `work/arch_raw.png`（`4:3` 横版，**纯白底 `#FFFFFF`**，左右拱脚在同一水平平底基线，拱洞下方纯白）：
     - 生日：彩字 `HAPPY BIRTHDAY` + 右上双气球。
     - 圣诞：手绘彩字 `MERRY CHRISTMAS` + 右上双圣诞挂球/松果冬青铃铛。
   - **左前立体道具（纯白底 `#FFFFFF`，平底落地，四周留净白边无孤立碎点）**：
     - 生日：`work/cake_raw.png`（`3:4` 竖版，折叠木桌椅 + 双层蛋糕 + 顶部正中唯一**未点燃**蜡烛）。
     - 圣诞：`work/tree_raw.png`（`3:4` 竖版，**不要画蛋糕**，改为同画风木盆/铁艺盆栽立体手绘圣诞树，树冠丰满对称、挂满圣诞球/松果/干橙/小礼盒，树顶有一颗醒目金色大星，由前端动态点亮常亮闪烁的暖光星星灯）。

### 路径 B：当前宿主 Agent 为纯命令行/代码型 Agent（无内置画图工具，如 Claude Code / Codex）

运行本技能包提供的多模型脚本（自动读取 `.env` 并调用百炼 / Gemini / OpenAI 兼容接口）：

1. **先安全检测环境配置**（严禁打印密钥值）：
   ```bash
   python scripts/ai_redraw.py --check-env
   ```
   - 若 `ready` 为 `false`，引导用户复制 `.env.example` 为 `.env` 并在终端安全填入密钥（绝不要让用户在聊天中发送明文密钥）。
2. **按主题与版式运行重绘**：
   ```bash
   # 生日 · 左右横版
   python scripts/ai_redraw.py --occasion birthday --fold horizontal --style-ref work/style_ref.jpg --portrait work/portrait.jpg --out-dir work

   # 生日 · 上下翻折 4:3 长方形版
   python scripts/ai_redraw.py --occasion birthday --fold vertical --style-ref work/style_ref.jpg --portrait work/portrait.jpg --out-dir work

   # 圣诞 · 上下翻折 4:3 长方形版（自动绘制圣诞树而非蛋糕）
   python scripts/ai_redraw.py --occasion christmas --fold vertical --style-ref work/style_ref.jpg --portrait work/portrait.jpg --out-dir work
   ```

---

## 第三步：纸艺刀模裁切与防穿模单文件 HTML 确定性组装

1. 确认已安装依赖（仅需 Pillow）：
   ```bash
   pip install -r requirements.txt
   ```
2. 按主题与版式运行 `scripts/build_card.py`。脚本自动执行：纯白底洪水抠图 + **自动清除角落零散杂点防错位** + 300g 米白卡纸刀模白边 + 烛芯坐标探测（生日）或树冠星灯锚点自动扫描（圣诞） + 真毛边棉麻底布按节日自动切换 + 单文件 HTML 封装：

```bash
# 1) 生日 · 左右横版
python scripts/build_card.py --occasion birthday --fold horizontal --work-dir work --style-ref work/style_ref.jpg --strict-redraw-check --output output/birthday_popup_card_horizontal.html

# 2) 生日 · 上下翻折 4:3 长方形版
python scripts/build_card.py --occasion birthday --fold vertical --work-dir work --style-ref work/style_ref.jpg --strict-redraw-check --output output/birthday_popup_card_vertical_4x3.html

# 3) 圣诞 · 左右横版（自动使用 work/tree_raw.png 与圣诞刺绣棉麻信）
python scripts/build_card.py --occasion christmas --fold horizontal --work-dir work --style-ref work/style_ref.jpg --strict-redraw-check --output output/christmas_popup_card_horizontal.html

# 4) 圣诞 · 上下翻折 4:3 长方形版
python scripts/build_card.py --occasion christmas --fold vertical --work-dir work --style-ref work/style_ref.jpg --strict-redraw-check --output output/christmas_popup_card_vertical_4x3.html
```

---

## 第四步：质量自检与交付给用户

交付前逐版检查：
1. **防穿模核对**：合上封面 -> 翻开中间态 -> 完全展开 -> 拖拽左右/上下旋转视角。确认左前道具（蛋糕或圣诞树）、中央人物、后景拱门与右前火漆信封 4 层层次分明，无任何穿模、劈穿底页或左右重叠；上下翻折版合上时是规整的 **4:3 横向长方形封面**，展开为 2:3 宽敞双页。
2. **双主题零穿帮核对**：
   - 生日版：八音盒《生日快乐歌》、蛋糕火焰对准烛芯、轻点直灭与长按 1 秒吹气正常、翻开零报错（HTTPS 链接自动弹手机麦克风授权且对吹气灵敏，本地离线文件静默零报错自动用轻点/长按兜底）、棉麻刺绣信为生日款。
   - 圣诞版：封面与拱门写 `Merry Christmas`、左前为常亮闪烁暖光星星灯圣诞树（点击树或“星灯”按钮绽放星光并飘落冬日雪花）、八音盒为《We Wish You a Merry Christmas》、棉麻刺绣信为小圣诞树 + `MERRY ~ CHRISTMAS !`、全程零“生日/蛋糕/蜡烛”字样。
3. **极简与零 Emoji 核对**：底部唯一单行胶囊条无滚动条、零 Emoji、无控制台报错。
4. 用温暖通俗的中文将成品 `.html` 文件路径与玩法说明交付给用户（提醒用户：若想让好友在手机上直接对着屏幕真吹气灭蜡烛，可将 HTML 放到任意 HTTPS 静态链接发给好友；若直接用微信发本地 HTML 附件，系统会静默免报错切换为轻点直灭或长按 1 秒仿真吹气）。
