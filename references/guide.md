# 画风重绘公式、审美铁律与双节日祝福模板

## 一、 六大审美铁律（出图必守）
1. **温润哑光纸本**：保持 300g 冷压水彩纸质感（`#faf6ec`）与细腻手绘轮廓，严禁 3D CGI 塑料反光、网红磨皮与荧光刺眼色。
2. **60-30-10 配色统一**：60% 纸白留白、30% 参考图主气氛色、10% 轻点缀；全套 5~6 张图必须色温与纸色完全一致。
3. **呼吸感留白**：封面留出 30%~40% 干净负空间托出主题字；展开内页中轴留出 50% 以上浅淡远景或小径，把浓密植物收敛到外缘四角。
4. **绘本肖像自然**：忠实保留真人五官、神态、发型穿搭与手势，完全转为封面同款手绘笔触，底部用一簇紧凑植物花环自然收边。
5. **优雅手写题字**：使用轻盈手写花体或手绘衬线体，严禁粗黑体、多余英文乱码或水印。
6. **打包前 6 项自检（单张不达标只重画该张）**：不抄袭参考原图；全套画风同师所画；白底立牌四周净白 `#FFFFFF` 无投影无角落飞点且平底对齐；内页中央通透不抢戏（上下拆页需检查折线接缝连贯）；生日为未点燃单蜡烛双层蛋糕、圣诞为金星立体圣诞树（绝不混用）；祝福语无乱码。

---

## 二、 全套英文重绘 Prompt 公式（先看参考图提取画风 `{MEDIUM}`、`{MOTIFS}`、`{PORTRAIT}`）
所有 Prompt 末尾统一追加审美护栏：`Warm matte storybook paper finish, 60-30-10 low-saturation natural palette, generous breathing whitespace, delicate hand-drawn outlines; NO glossy 3D CGI plastic sheen, NO neon colors, NO watermarks.`

1. **全新封面**（横版 3:4 存 `cover_raw.png`；上下 4:3 版存 `cover_vertical_raw.png`）
   - 生日：`Brand-new original {3:4 portrait / 4:3 landscape} birthday card cover in exact {MEDIUM}, motifs of {MOTIFS}. Graceful hand-lettered 'Happy Birthday' in quiet upper space (35% breathing room). Do NOT copy original reference layout or brand text. Flat 2D full-bleed art.`
   - 圣诞：将 `birthday` 换为 `Christmas`，题字换为 `Merry Christmas`。
2. **中央人物立牌**（3:4 纯白底存 `character_raw.png`）
   - `Waist-up pop-up card standee preserving exact likeness, warm smile, hairstyle, outfit and pose of {PORTRAIT}, completely re-illustrated in exact {MEDIUM}. Tuck bottom waist into a compact curved floral cluster of {MOTIFS}. Pure flat solid #FFFFFF white background, generous margins, zero drop shadows, zero corner specks.`
3. **展开内页**
   - 横版 3:2 单图（存 `inside_raw.png`）：`Wide 3:2 flat greeting card inside spread in exact {MEDIUM} matching the new cover. Frame outer edges with {MOTIFS}, keep center calm low-contrast distant scenery and pale path on warm cream paper. No people, no cake, no tree, no text.`
   - 上下 4:3 版 · 方案 A（推荐，单张 2:3 连续上下内页，存 `inside_vertical_raw.png`）：`Vertical 2:3 continuous flat greeting card inside spread in exact {MEDIUM} matching the new cover. Place lush {MOTIFS} around outer borders while keeping the middle 55% quiet pale scenery and a gentle path crossing the horizontal center fold cleanly. No people, no cake, no tree, no text.`
   - 上下 4:3 版 · 方案 B（两张 4:3 衔接上下内页，先画 `inside_top.png` 再衔接画 `inside_bottom.png`）：
     - 上半页 `inside_top.png`：`Flat full-bleed 4:3 upper inside page matching the new cover in exact {MEDIUM}, framing top and side borders with {MOTIFS}, leaving quiet pale sky/scenery along the bottom fold edge so it joins the lower page seamlessly. No people, no cake, no tree, no text.`
     - 下半页 `inside_bottom.png`：`Flat full-bleed 4:3 lower inside page continuing seamlessly from inside_top.png's top fold edge in exact {MEDIUM}, extending the gentle path forward with lush {MOTIFS} along side and bottom borders. No people, no cake, no tree, no text.`
4. **后景花环拱门**（4:3 纯白底存 `arch_raw.png`）
   - 生日：`Semicircular botanical pop-up birthday archway in exact {MEDIUM} with {MOTIFS}, arched lettering 'HAPPY BIRTHDAY' along top curve and two festive balloons at top-right. Flat level feet on one baseline. Pure flat solid #FFFFFF white background including open center below arch, zero shadows, zero corner specks.`
   - 圣诞：题字换 `MERRY CHRISTMAS`，气球换 `two vintage Christmas baubles`。
5. **左前节日道具**（3:4 纯白底）
   - 生日蛋糕（存 `cake_raw.png`）：`Hand-painted {MEDIUM} pop-up standee of a rustic wooden garden table and tucked chair holding a two-tier frosted birthday cake, ONE centered upright striped candle ending in a short unlit dark wick. CRITICAL: NO fire, NO flame, NO glow. Level baseline, pure solid #FFFFFF background, zero shadows, zero corner specks.`
   - 圣诞树（存 `tree_raw.png`）：`Hand-painted {MEDIUM} pop-up standee of a lush miniature Christmas tree in a rustic wooden planter pot with vintage ornaments, berries, tiny ribbons and a gold star topper. Flat level pot base, pure solid #FFFFFF background, zero shadows, zero corner specks.`

---

## 三、 双节日祝福语模板（`blessing.json` 规范）
- `blessing.json` 必须为 JSON 对象：`{"recipient":"称呼：","lines":["句子1","句子2"],"closing":"结尾祝词","signature":"落款","subSignature":"日期(选填)"}`。
- 建议正文 3~7 行、100 字以内留白最佳；若用户写得很长也完整保留，前端会自动在棉麻布内平滑上下滑动。
- **生日默认模板**：抬头 `亲爱的[称呼]：`；正文 `["又长大一岁啦，愿新岁的每一天", "都有温暖的风吹散烦恼", "愿你永远被爱包围", "平安顺遂，自在闪耀"]`（用户若有补充句可插在中间）；结语 `生日快乐，万事胜意！`。
- **圣诞默认模板**：抬头 `亲爱的[称呼]：`；正文 `["雪花轻落窗台，圣诞灯火正暖", "愿今年所有的温柔与期盼", "都化作冬日里的星光与好运", "平安顺遂，温暖常伴左右"]`；结语 `圣诞快乐，冬日安暖！`。
