# 画风拆解标准与全套素材重绘 Prompt 规范（支持生日 / 圣诞 & 左右 / 上下 4:3 版式）

> **核心原则**：用户上传的“贺卡封面参考图”（横图、竖图都不受限）只用来提取 **画风媒介、色彩体系与装饰元素**；必须据此从零重新绘制全新节日封面，并用同一套画风重绘真人人物、展开内页、花环拱门与节日立体道具。**严禁直接把参考封面原图或未经重绘的生活照硬贴进成品！**

---

## 一、 视觉分析输出清单（`work/style_profile.json`）

请视觉模型对照 **【图 A：封面参考图】** 和 **【图 B：真人照片】** 提取以下字段：

| 字段名 | 提取重点（大白话说明） | 注意事项 |
| :--- | :--- | :--- |
| `art_medium_en` | 绘画媒介、笔触、线条描边、纸面质感 | 例如手绘水彩+细棕墨线、厚涂粉彩插画、日系彩铅手账等 |
| `paper_texture_en` | 纸张底色与颗粒质感 | 例如温暖米白冷压水彩纸 `#faf6ec` |
| `decorative_motifs_en` | 封面中可复用的花草、松果、建筑、小物件 | **过滤并丢弃**参考图原本的品牌字样、不相干字母或他人人物 |
| `cover_scene_idea_en` | 全新构思的节日封面画面描述 | 生日突出 `Happy Birthday`，圣诞突出 `Merry Christmas`（加入冬青、雪松、星星灯、礼物、温暖木屋等圣诞意象） |
| `portrait_identity_en` | 真人照片人物外貌与动作拆解 | 精确记录脸型五官、微笑神态、发型发饰、穿搭颜色、手持物品与动作 |
| `styleTheme` | 全局协调色盘（HEX） | `tableInner`、`tableOuter`、`primaryAccent`、`secondaryAccent`、`waxSealColor` |

---

## 二、 全套全新重绘素材的黄金 Prompt 公式

### 1A. 左右横版封面 (`work/cover_raw.png`, 比例 `3:4` 竖版)
> **参考图输入**：传入【封面参考图】定画风。
> - **生日模式**：手写花体文字为 `"Happy Birthday"`。
> - **圣诞模式**：手写花体文字为 `"Merry Christmas"`，融入温暖圣诞树/松果/红果/暖光星灯/飘雪氛围。
>
> **Prompt**：
> ```text
> Create a BRAND-NEW original vertical 3:4 {birthday OR Christmas} greeting card cover illustration strictly matching the exact artistic medium, brushwork, line weight, and paper texture of the style reference ({art_medium_en}, {paper_texture_en}).
> Scene: {cover_scene_idea_en}
> Decorative botanical/scenic border elements inspired by {decorative_motifs_en}.
> Feature graceful, legible hand-lettered artistic calligraphy reading "{Happy Birthday OR Merry Christmas}" integrated harmoniously in the upper-center negative space.
> CRITICAL RULES:
> - DO NOT copy, trace, or paste the exact layout or original unrelated words from the reference image.
> - No fingers, no tabletop margins, no tilted angle, flat straight-on full-bleed 3:4 card artwork only.
> ```

### 1B. 上下翻折版封面 (`work/cover_vertical_raw.png`, **标准 `4:3` 横向长方形**)
> **核心要求**：无论用户上传的参考封面是竖图还是横图，制作上下翻折版时必须重绘为 **标准 4:3 横向长方形矩形封面**，保证横竖两版风格完全一致且打开后宽敞舒展。
>
> **Prompt**：
> ```text
> Create a BRAND-NEW original horizontal landscape 4:3 rectangular {birthday OR Christmas} greeting card cover illustration strictly matching the exact artistic medium, brushwork, line weight, and paper texture of the style reference ({art_medium_en}, {paper_texture_en}).
> Compose a balanced horizontal 4:3 scenic layout with {decorative_motifs_en} framing the left, right, and bottom edges harmoniously.
> Feature graceful, legible hand-lettered artistic calligraphy reading "{Happy Birthday OR Merry Christmas}" prominently in the upper-center negative space.
> CRITICAL RULES:
> - Full-bleed flat straight-on 4:3 landscape card cover only; no fingers, no tilted perspective, no tabletop margins, no unrelated text.
> ```

### 2. 中央立体弹出真人人物 (`work/character_raw.png`, 比例 `3:4` 竖版)
> **参考图输入**：同时传入【封面参考图（定画风）】与【真人照片（定外貌动作）】。
>
> **Prompt**：
> ```text
> Waist-up character illustration for a paper pop-up {birthday OR Christmas} card standee.
> IDENTITY LOCK: Faithfully preserve the exact facial likeness, gentle facial expression, hair style, clothing, jewelry/hairpins, and hand pose of the person in the portrait reference: {portrait_identity_en}.
> STYLE LOCK: Completely re-illustrate the person strictly in the exact artistic medium, brushwork, outline thickness, and harmonious color palette of the cover style reference ({art_medium_en}). Do NOT leave any raw photographic skin or photographic textures.
> COMPOSITION & DIE-CUT ISOLATION RULES:
> - Center the waist-up figure with generous clean whitespace margins on all four sides (top, left, right, bottom).
> - Tuck the bottom edge of the torso neatly into a compact curved botanical base cluster inspired by {decorative_motifs_en} (add holly berries/pine sprigs for Christmas) so the bottom cuts off cleanly as a curved standee base.
> - Pure flat solid white background (#FFFFFF) around the entire perimeter with ZERO stray dots, zero floating flecks, zero drop shadows, zero text.
> ```

### 3A. 左右横版展开双页内页 (`work/inside_raw.png`, 比例 `3:2` 横幅)
> **Prompt**：
> ```text
> Wide 3:2 flat greeting card inside spread artwork strictly matching the exact {art_medium_en} style and color palette of the new card cover.
> Frame the outer edges with rich motifs from {decorative_motifs_en}. Extend a pale low-contrast continuous landscape across the center and side openings: distant trees/sky, low planting, and a gentle curving garden path.
> Keep the middle area soft, bright, and airy over {paper_texture_en} so pop-up standees read clearly.
> Strictly NO people, NO center cake, NO center tree, NO text, straight-on flat 2D surface view.
> ```

### 3B. 上下翻折 4:3 版展开连续内页 (`work/inside_vertical_raw.png`, **比例 `2:3` 竖向双页 = 上 `4:3` + 下 `4:3`**)
> **Prompt**：
> ```text
> Vertical 2:3 flat greeting card inside spread artwork (designed to fold horizontally right across the exact center line into an upper 4:3 page and a lower 4:3 page) strictly matching the exact {art_medium_en} style and color palette of the new card cover.
> Frame the upper border and left/right edges of the top half with rich {decorative_motifs_en}, and frame the bottom border and left/right edges of the lower half with rich {decorative_motifs_en}.
> Across the middle fold zone and central area, paint a soft, low-contrast pale watercolor landscape with distant scenery on the upper half transitioning seamlessly across the horizontal center fold into a gentle garden path / snowy lane on the lower half.
> Strictly NO people, NO center cake, NO center tree, NO text, straight-on flat 2D artwork only.
> ```

### 4. 后景立体花环拱门 (`work/arch_raw.png`, 比例 `4:3` 横版)
> **Prompt（生日模式）**：
> ```text
> Semicircular paper pop-up birthday archway standee in the exact {art_medium_en} style.
> Botanical arch made of {decorative_motifs_en}, curving across the upper arc with joyful colorful hand-lettered arch text reading "HAPPY BIRTHDAY" and two festive balloons floating near the top-right shoulder.
> Both feet have a broad flat lower edge on one level horizontal baseline. Pure flat solid white background (#FFFFFF) around the outside AND pure solid white (#FFFFFF) inside the lower arch opening. ZERO stray white/colored dots, zero shadows.
> ```
>
> **Prompt（圣诞模式）**：
> ```text
> Semicircular paper pop-up Christmas archway standee in the exact {art_medium_en} style.
> Evergreen pine, cedar, holly leaves, red berries, pinecones, and warm winter botanicals matching {decorative_motifs_en}, curving across the upper arc with charming hand-lettered arch text reading "MERRY CHRISTMAS" and two glossy festive Christmas ornaments/baubles hanging gracefully near the top-right shoulder.
> Both feet have a broad flat lower edge on one level horizontal baseline. Pure flat solid white background (#FFFFFF) outside AND pure solid white (#FFFFFF) inside the lower arch opening. ZERO stray speckles, zero shadows, NO birthday text.
> ```

### 5A. 生日左前立体道具：双层蛋糕与折叠木桌椅 (`work/cake_raw.png`, 比例 `3:4` 竖版)
> **Prompt**：
> ```text
> Hand-painted {art_medium_en} pop-up standee piece showing a rustic wooden garden folding table with a small wooden chair beside it, holding a charming two-tier frosted birthday cake decorated with seasonal berries matching the card's palette.
> CRITICAL CANDLE RULE:
> - Place ONE vertical striped birthday candle centered right at the very top of the cake, ending in a short unlit dark cotton wick.
> - DO NOT draw any fire, flame, glow, or smoke on the candle (dynamic Web flame will render right at the wick tip).
> Compose cake and furniture as one compact upright group with all lowest feet on one level baseline. Pure flat solid white background (#FFFFFF) with clean narrow margins, zero stray flecks, zero shadows, zero text.
> ```

### 5B. 圣诞左前立体道具：手绘星星灯立体圣诞树 (`work/tree_raw.png`, 比例 `3:4` 竖版，**取代蛋糕**)
> **Prompt**：
> ```text
> Hand-painted {art_medium_en} pop-up standee piece showing a charming, lush miniature potted Christmas tree in a rustic wooden tub / vintage terracotta planter, styled strictly to match the exact watercolor/ink medium and warm festive palette of the Christmas card cover.
> Decorate the rich evergreen pine branches with classic miniature red and gold baubles, tiny pinecones, dried orange slices, delicate warm ribbons, and a prominent bright golden five-pointed star topper perched straight at the very top peak of the tree.
> Place two tiny hand-wrapped gift boxes tucked tightly against the flat base of the wooden pot on one level horizontal baseline so the whole silhouette is sturdy and compact.
> CRITICAL DIE-CUT RULES:
> - Pure flat solid white background (#FFFFFF) on all four sides with generous clean margins.
> - ZERO floating snowflakes, zero loose dots, zero cast shadows on the white background, zero text, NO birthday cake, NO candles.
> - Leave clear lush dark-green pine foliage across the tiers so interactive twinkling star fairy lights overlaid by the web engine shine vividly against the tree.
> ```
