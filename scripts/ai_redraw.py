"""
AI 视觉画风识别与全套重绘流水线引擎（Birthday Pop-up Card Skill 可选自动化引擎）

通俗用途说明：
1. 本脚本专为【自身没有内置看图与画图工具的纯命令行 Agent（如 Claude Code / Codex / CLI）】设计。
   （如果当前使用的 Agent 如 Antigravity 或多模态千问自身就能看图画图，可直接跳过本脚本，由 Agent 画完后直接运行 build_card.py 即可。）
2. 本脚本仅使用 Python 标准库发起网络请求（零多余第三方网络依赖），默认支持：
   - 阿里云百炼 DashScope（通义千问视觉 qwen-vl-max + 万相/千问生图 wan2.6-image / qwen-image-3.0-pro）
   - Google Gemini API（多模态识图 + 图像生成重绘）
   - 任意 OpenAI 兼容接口
3. 严格执行“先看懂画风 -> 再按画风从零重绘新封面、新人物立牌、新内页、新拱门、新蛋糕”流程，绝不把参考图原封不动贴到封面上。
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image


SKILL_ROOT = Path(__file__).resolve().parent.parent

# 跨模型通用审美护栏：锁定哑光绘本纸本质感、60-30-10 克制配色与呼吸感留白，严禁 3D 塑料光感与荧光刺眼色
AESTHETIC_GUARD_EN = (
    "AESTHETIC GUARDRAILS: Warm matte storybook paper finish with harmonious 60-30-10 low-saturation natural palette, "
    "generous calm breathing whitespace, delicate organic hand-drawn contours and subtle paper tooth. "
    "STRICTLY FORBIDDEN: glossy 3D CGI plastic sheen, neon oversaturated colors, waxy airbrushed portrait skin, "
    "overcrowded noisy backgrounds, gibberish extra letters or watermarks."
)


def sanitize_secret_text(text: Any) -> str:
    """
    对错误响应正文、异常消息及 URL 进行彻底脱敏，确保任何 API Key、Token 或占位符密钥绝不被原样泄露。
    """
    cleaned = str(text or "")
    secret_env_names = {
        "DASHSCOPE_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }
    for env_k, env_v in os.environ.items():
        val = (env_v or "").strip()
        if not val:
            continue
        if env_k in secret_env_names or (len(val) >= 6 and any(tag in env_k.upper() for tag in ("KEY", "TOKEN", "SECRET", "PASS"))):
            cleaned = cleaned.replace(val, "[REDACTED]")

    patterns = (
        (r"(?i)(bearer\s+)[^\s\"',}]+", r"\1[REDACTED]"),
        (r"(?i)([?&](?:api_)?key=)[^&\s\"',}]+", r"\1[REDACTED]"),
        (r"(?i)([\"']?(?:api_?key|authorization|x-api-key|secret|access_token|token)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+", r"\1[REDACTED]"),
        (r"\bsk-[A-Za-z0-9_-]{4,}\b", "[REDACTED]"),
        (r"\bAIza[A-Za-z0-9_-]{8,}\b", "[REDACTED]"),
    )
    for pat, repl in patterns:
        cleaned = re.sub(pat, repl, cleaned)
    return cleaned


def load_env_files() -> None:
    """
    从当前目录、Skill 仓库根目录以及用户主目录安全读取 .env 配置到进程环境变量。
    绝不覆盖已有的系统环境变量，且绝不在日志里输出任何密钥值。
    """
    candidates = [
        Path.cwd() / ".env",
        SKILL_ROOT / ".env",
        Path.home() / ".env",
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ and val:
                        os.environ[key] = val
        except OSError:
            pass


def check_env_status() -> Dict[str, Any]:
    """
    安全检测当前可用的模型接口（绝不打印任何 API Key 明文）。
    """
    load_env_files()
    configured = {
        "dashscope": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }
    preferred = os.environ.get("CARD_AI_PROVIDER", "dashscope").lower().strip()
    if preferred not in configured or not configured[preferred]:
        for name, ok in configured.items():
            if ok:
                preferred = name
                break
    return {
        "provider": preferred,
        "ready": any(configured.values()),
        "configured": configured,
    }


def encode_image_b64(img_path: str, max_dim: int = 1280) -> Tuple[str, str]:
    """
    读取本地图片，等比缩放到合理清晰度并返回 (mime_type, base64_str)。
    """
    img = Image.open(img_path)
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "image/jpeg", b64


def http_json_request(
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: str = "POST",
    timeout: int = 120,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """发起标准 HTTP JSON 请求（对 429/502/503/504 限流抖动自动退避重试，异常响应与 URL 统一脱敏）。"""
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    ctx = ssl.create_default_context()
    safe_url = sanitize_secret_text(url.split("?")[0])
    retry_codes = {429, 502, 503, 504}

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass
            if err.code in retry_codes and attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            safe_body = sanitize_secret_text(body)
            raise RuntimeError(f"HTTP {err.code} 请求失败 ({safe_url}): {safe_body}") from None
        except urllib.error.URLError as err:
            if attempt < max_retries:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise RuntimeError(f"网络连接失败 ({safe_url}): {sanitize_secret_text(err.reason)}") from None
        except Exception as err:
            raise RuntimeError(f"接口请求异常 ({safe_url}): {sanitize_secret_text(err)}") from None
    raise RuntimeError(f"接口请求重试耗尽 ({safe_url})")


def save_image_from_result(result_ref: str, out_path: str) -> None:
    """将模型返回的图片 URL 或 base64 DataURI 保存到本地图片文件（异常均脱敏）。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if result_ref.startswith("data:image/"):
        _, b64_part = result_ref.split(",", 1)
        raw = base64.b64decode(b64_part)
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.save(out_path, "PNG", optimize=True)
        return

    req = urllib.request.Request(result_ref, headers={"User-Agent": "BirthdayPopupCardSkill/1.0"})
    ctx = ssl.create_default_context()
    safe_ref = sanitize_secret_text(result_ref.split("?")[0])
    try:
        with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
            raw = resp.read()
    except Exception as err:
        raise RuntimeError(f"下载生成图片失败 ({safe_ref}): {sanitize_secret_text(err)}") from None
    img = Image.open(BytesIO(raw)).convert("RGB")
    img.save(out_path, "PNG", optimize=True)


def extract_json_block(text: str) -> Dict[str, Any]:
    """从视觉模型回复文本中稳健提取 JSON 对象。"""
    cleaned = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def analyze_with_vlm(
    provider: str,
    style_ref_path: str,
    portrait_path: str,
    occasion: str = "birthday",
) -> Dict[str, Any]:
    """
    调用视觉理解大模型（Qwen-VL / Gemini / GPT-4o）同时读取【封面参考图】与【真人照片】，
    输出结构化的画风 DNA、调色盘、以及人物外貌特征描述（绝不把旧封面照抄当新封面）。
    """
    mime_style, b64_style = encode_image_b64(style_ref_path)
    mime_port, b64_port = encode_image_b64(portrait_path)
    is_christmas = occasion == "christmas"
    card_kind = "Christmas" if is_christmas else "birthday"
    greeting_text = "Merry Christmas" if is_christmas else "Happy Birthday"

    analysis_prompt = f"""You are a senior storybook art director. Inspect Image 1 (Cover Style Reference) and Image 2 (Real Person Portrait).
Return ONLY a valid JSON object (no markdown commentary) matching this exact schema:
{{
  "art_medium_en": "Detailed English description of Image 1's artistic medium, brushwork, line ink style, shading, and paper grain",
  "paper_texture_en": "Cold-press watercolor paper or matte cardstock texture and color tone description",
  "decorative_motifs_en": "Key visual motifs, flora, props, and mood inspired by Image 1 (DO NOT include any text/words/brands from Image 1)",
  "cover_scene_idea_en": "A BRAND-NEW original {card_kind} greeting card illustration scene composed in Image 1's exact art medium and motifs, with graceful space at top for '{greeting_text}' lettering (DO NOT copy Image 1 literally)",
  "portrait_identity_en": "Accurate objective description of the person in Image 2: age range, facial features, warm expression, hairstyle, hair color, accessories/earring/hairpin, clothing style/colors, and objects/pose in hands",
  "styleTheme": {{
    "styleName": "简短中文风格名称（例如：{'暖意冬日圣诞风' if is_christmas else '暖意森林水彩风'}）",
    "tableInner": "#xxxxxx (soft light tabletop inner color harmonious with style)",
    "tableOuter": "#xxxxxx (soft slightly deeper tabletop outer color)",
    "paperCream": "#faf6ec",
    "primaryAccent": "#xxxxxx (main botanical/theme accent color)",
    "secondaryAccent": "#xxxxxx (flower/highlight accent color)",
    "waxSealColor": "#xxxxxx (rich wax seal crimson or accent hex)",
    "filterCss": "none"
  }}
}}"""

    if provider == "dashscope":
        api_key = os.environ["DASHSCOPE_API_KEY"]
        base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
        model = os.environ.get("DASHSCOPE_VISION_MODEL", "qwen-vl-max")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime_style};base64,{b64_style}"}},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_port};base64,{b64_port}"}},
                        {"type": "text", "text": analysis_prompt},
                    ],
                }
            ],
            "temperature": 0.3,
        }
        res = http_json_request(
            f"{base_url}/compatible-mode/v1/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        content = res["choices"][0]["message"]["content"]
        return extract_json_block(content)

    if provider == "gemini":
        api_key = os.environ["GEMINI_API_KEY"]
        model = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inlineData": {"mimeType": mime_style, "data": b64_style}},
                        {"inlineData": {"mimeType": mime_port, "data": b64_port}},
                        {"text": analysis_prompt},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        res = http_json_request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            payload=payload,
        )
        text = res["candidates"][0]["content"]["parts"][0]["text"]
        return extract_json_block(text)

    if provider == "openai":
        api_key = os.environ["OPENAI_API_KEY"]
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime_style};base64,{b64_style}"}},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_port};base64,{b64_port}"}},
                        {"type": "text", "text": analysis_prompt},
                    ],
                }
            ],
            "temperature": 0.3,
        }
        res = http_json_request(
            f"{base_url}/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        content = res["choices"][0]["message"]["content"]
        return extract_json_block(content)

    raise ValueError(f"不支持的模型服务商: {provider}")


def generate_image_dashscope(
    prompt: str,
    ref_images: List[str],
    size_str: str,
) -> str:
    """
    调用阿里云百炼 DashScope 图像生成/编辑接口（支持参考图风格重绘）。
    优先使用同步/多模态接口（wan2.6-image / qwen-image-3.0-pro），并自动兼容异步 task_id 轮询与 t2i 回退。
    """
    api_key = os.environ["DASHSCOPE_API_KEY"]
    base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
    model = os.environ.get("DASHSCOPE_IMAGE_MODEL", "wan2.6-image")

    def extract_image_url(data: Dict[str, Any]) -> Optional[str]:
        output = data.get("output") or {}
        choices = output.get("choices") or []
        if choices:
            msg_content = (choices[0].get("message") or {}).get("content") or []
            for item in msg_content:
                if isinstance(item, dict) and item.get("image"):
                    return item["image"]
        results = output.get("results") or []
        if results and isinstance(results[0], dict) and results[0].get("url"):
            return results[0]["url"]
        return None

    def poll_task(task_id: str) -> str:
        task_url = f"{base_url}/api/v1/tasks/{task_id}"
        for _ in range(60):
            time.sleep(2.5)
            status_res = http_json_request(
                task_url,
                payload=None,
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            st = (status_res.get("output") or {}).get("task_status", "")
            if st == "SUCCEEDED":
                img_url = extract_image_url(status_res)
                if img_url:
                    return img_url
                raise RuntimeError("百炼异步生图任务完成，但响应中未找到图片地址")
            if st in ("FAILED", "CANCELED"):
                raise RuntimeError(f"百炼生图任务失败: {sanitize_secret_text(status_res)}")
        raise TimeoutError("百炼生图任务轮询超时")

    content_blocks: List[Dict[str, str]] = []
    for path in ref_images:
        mime, b64 = encode_image_b64(path, max_dim=1024)
        content_blocks.append({"image": f"data:{mime};base64,{b64}"})
    content_blocks.append({"text": prompt})

    endpoint_mm = f"{base_url}/api/v1/services/aigc/multimodal-generation/generation"
    payload_mm = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content_blocks}]},
        "parameters": {"size": size_str, "watermark": False, "prompt_extend": True},
    }

    try:
        res = http_json_request(
            endpoint_mm,
            payload=payload_mm,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=150,
        )
        img_url = extract_image_url(res)
        if img_url:
            return img_url
        task_id = (res.get("output") or {}).get("task_id")
        if task_id:
            return poll_task(task_id)
    except Exception as mm_err:
        # 含参考图的重绘若失败，不再静默丢失参考约束；仅无参考图时才兼容纯异步 t2i
        if ref_images:
            raise RuntimeError(f"百炼参考图重绘接口失败，为保证画风与人物约束未回退纯文本生图: {sanitize_secret_text(mm_err)}") from None
        fallback_model = os.environ.get("DASHSCOPE_T2I_FALLBACK_MODEL", "wanx2.1-t2i-turbo")
        endpoint_t2i = f"{base_url}/api/v1/services/aigc/text2image/image-synthesis"
        payload_t2i = {
            "model": fallback_model,
            "input": {"prompt": prompt},
            "parameters": {"size": size_str, "n": 1},
        }
        try:
            res2 = http_json_request(
                endpoint_t2i,
                payload=payload_t2i,
                headers={"Authorization": f"Bearer {api_key}", "X-DashScope-Async": "enable"},
                timeout=120,
            )
            task_id2 = (res2.get("output") or {}).get("task_id")
            if task_id2:
                return poll_task(task_id2)
            img_url2 = extract_image_url(res2)
            if img_url2:
                return img_url2
        except Exception as fb_err:
            raise RuntimeError(
                f"百炼生图均未成功。主接口: {sanitize_secret_text(mm_err)}; 回退接口: {sanitize_secret_text(fb_err)}"
            ) from None

    raise RuntimeError("未能从 DashScope 响应中解析出生成图片")


def generate_image_gemini(prompt: str, ref_images: List[str], aspect_ratio: str) -> str:
    """调用 Google Gemini 多模态生图重绘接口。"""
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    parts: List[Dict[str, Any]] = []
    for path in ref_images:
        mime, b64 = encode_image_b64(path, max_dim=1024)
        parts.append({"inlineData": {"mimeType": mime, "data": b64}})
    parts.append({"text": f"{prompt}\nAspect ratio: {aspect_ratio}."})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    res = http_json_request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        payload=payload,
        timeout=150,
    )
    for cand in res.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                mime_out = inline.get("mimeType", "image/png")
                return f"data:{mime_out};base64,{inline['data']}"
    raise RuntimeError(f"Gemini 未返回图像数据: {sanitize_secret_text(res)}")


def _map_openai_size(size_str: str) -> str:
    """根据 W*H 或 WxH 比例字符串精准映射至 OpenAI 支持的横/竖/方画幅。"""
    m = re.match(r"^\s*(\d+)\s*[*xX]\s*(\d+)\s*$", size_str or "")
    if not m:
        return "1024x1024"
    w_val, h_val = int(m.group(1)), int(m.group(2))
    if w_val > h_val:
        return "1536x1024"
    if h_val > w_val:
        return "1024x1536"
    return "1024x1024"


def generate_image_openai(prompt: str, ref_images: List[str], size_str: str) -> str:
    """调用 OpenAI 兼容图像生成/编辑接口（含参考图编辑严格报错保护及异常响应脱敏）。"""
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    oa_size = _map_openai_size(size_str)

    if ref_images:
        # 构造 multipart/form-data 调用 /images/edits 传入参考图
        boundary = f"----CardSkillBoundary{uuid.uuid4().hex}"
        chunks: List[bytes] = []

        def add_field(name: str, val: str) -> None:
            chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode("utf-8"))

        add_field("model", model)
        add_field("prompt", prompt)
        add_field("size", oa_size)

        for idx, path in enumerate(ref_images):
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            fname = Path(path).name
            field_name = "image[]" if len(ref_images) > 1 else "image"
            with open(path, "rb") as f:
                raw_bytes = f.read()
            header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"; filename="{fname}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
            chunks.append(header + raw_bytes + b"\r\n")

        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(chunks)

        req = urllib.request.Request(
            f"{base_url}/images/edits",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                item = res["data"][0]
                if item.get("b64_json"):
                    return f"data:image/png;base64,{item['b64_json']}"
                return item["url"]
        except urllib.error.HTTPError as err:
            err_body = ""
            try:
                err_body = err.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass
            raise RuntimeError(
                f"OpenAI 参考图重绘接口 (/images/edits) 返回 HTTP {err.code}，"
                f"为保证画风与人物参考约束未回退纯文本生图: {sanitize_secret_text(err_body)}"
            ) from None
        except Exception as err:
            raise RuntimeError(
                f"OpenAI 参考图重绘接口 (/images/edits) 失败，"
                f"为保证画风与人物参考约束未回退纯文本生图: {sanitize_secret_text(err)}"
            ) from None

    res = http_json_request(
        f"{base_url}/images/generations",
        payload={"model": model, "prompt": prompt, "size": oa_size},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=150,
    )
    item = res["data"][0]
    if item.get("b64_json"):
        return f"data:image/png;base64,{item['b64_json']}"
    return item["url"]


def run_redraw_asset(
    provider: str,
    prompt: str,
    ref_images: List[str],
    dashscope_size: str,
    aspect_ratio: str,
    out_path: str,
) -> None:
    """统一分发到所选模型提供商执行重绘并落地保存图片。"""
    if provider == "dashscope":
        ref = generate_image_dashscope(prompt, ref_images, dashscope_size)
    elif provider == "gemini":
        ref = generate_image_gemini(prompt, ref_images, aspect_ratio)
    elif provider == "openai":
        ref = generate_image_openai(prompt, ref_images, dashscope_size)
    else:
        raise ValueError(f"未知提供商: {provider}")
    save_image_from_result(ref, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="全套画风识别与立体贺卡素材 AI 重绘工具（支持生日/圣诞双主题与横/4:3上下双版式）")
    parser.add_argument("--check-env", action="store_true", help="安全检查 API 密钥配置状态（绝不打印密钥明文）")
    parser.add_argument("--style-ref", help="用户上传的贺卡封面风格参考图路径（横图或竖图均可）")
    parser.add_argument("--portrait", help="用户上传的真人照片路径")
    parser.add_argument("--occasion", choices=("birthday", "christmas"), default="birthday", help="节日主题：birthday | christmas")
    parser.add_argument("--fold", choices=("horizontal", "vertical"), default="horizontal", help="翻折版式：horizontal（左右）| vertical（4:3 横向长方形上下折）")
    parser.add_argument("--out-dir", default="work", help="重绘素材输出工作目录（默认 work/）")
    parser.add_argument("--provider", help="强制指定模型提供商：dashscope | gemini | openai")
    parser.add_argument(
        "--steps",
        default="analyze,cover,character,inside,arch,prop",
        help="要执行的阶段，逗号分隔（prop 等价于生日 cake 或圣诞 tree）",
    )
    args = parser.parse_args()

    if args.check_env:
        print(json.dumps(check_env_status(), ensure_ascii=False, indent=2))
        return

    if not args.style_ref or not args.portrait:
        parser.error("执行重绘时必须提供 --style-ref 和 --portrait 参数")

    env_info = check_env_status()
    provider = args.provider or env_info["provider"]
    if not env_info["configured"].get(provider):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"缺少 {provider} 的 API 密钥，请先按安全指引配置 .env 或由自带生图能力的宿主 Agent 直接绘出图片。",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps = {s.strip() for s in args.steps.split(",") if s.strip()}
    profile_path = out_dir / "style_profile.json"
    is_christmas = args.occasion == "christmas"
    vertical = args.fold == "vertical"
    greeting_title = "Merry Christmas" if is_christmas else "Happy Birthday"
    greeting_upper = "MERRY CHRISTMAS" if is_christmas else "HAPPY BIRTHDAY"
    card_theme_en = "Christmas" if is_christmas else "birthday"

    if "analyze" in steps or not profile_path.is_file():
        print("[1/6] 正在通过视觉大模型分析参考图画风与人物特征...")
        profile = analyze_with_vlm(provider, args.style_ref, args.portrait, occasion=args.occasion)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    else:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

    art_medium = profile.get("art_medium_en", "warm hand-painted storybook watercolor with fine brown ink outlines")
    paper_tex = profile.get("paper_texture_en", "300gsm textured warm cream cold-press watercolor paper (#faf6ec)")
    motifs = profile.get("decorative_motifs_en", "lush botanical foliage and blossoms")
    cover_scene = profile.get("cover_scene_idea_en", f"enchanting storybook {card_theme_en} garden")
    portrait_desc = profile.get("portrait_identity_en", "friendly smiling person waist-up")

    def run_parallel_batch(batch_name: str, tasks: List[Tuple[str, Any]]) -> None:
        """按批次并发执行互不依赖的重绘任务，减少排队等待时间。"""
        if not tasks:
            return
        if len(tasks) == 1:
            tasks[0][1]()
            return
        print(f"[并行加速] {batch_name}：同时生成 {', '.join(name for name, _ in tasks)}...")
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            future_map = {pool.submit(fn): name for name, fn in tasks}
            errors: List[str] = []
            for fut in as_completed(future_map):
                t_name = future_map[fut]
                try:
                    fut.result()
                except Exception as exc:
                    errors.append(f"{t_name}: {sanitize_secret_text(exc)}")
            if errors:
                raise RuntimeError(f"{batch_name}部分重绘失败 -> " + " | ".join(errors))

    # ==================== 第 1 批并行：封面 + 人物（均只依赖原始参考图） ====================
    batch1: List[Tuple[str, Any]] = []
    if "cover" in steps:
        cover_file = "cover_vertical_raw.png" if vertical else "cover_raw.png"
        cover_size = "1280*960" if vertical else "960*1280"
        cover_ratio = "4:3" if vertical else "3:4"
        orient_en = "horizontal landscape 4:3" if vertical else "vertical portrait 3:4"
        p_cover = (
            f"Create a BRAND-NEW original {orient_en} {card_theme_en} greeting card cover illustration strictly matching "
            f"the artistic medium and brushwork of the attached style reference ({art_medium}, {paper_tex}). "
            f"Scene: {cover_scene}. Border motifs inspired by {motifs}. "
            f"Feature graceful hand-lettered artistic typography reading '{greeting_title}' cleanly in the upper space (leave 30-40% quiet breathing negative space). "
            f"DO NOT copy or paste the original reference layout or any unrelated original text. Full-bleed flat 2D card art. "
            f"{AESTHETIC_GUARD_EN}"
        )
        batch1.append(("全新封面", lambda: (
            print(f"[2/6] 正在按提取画风从零重绘全新《{greeting_title}》{cover_ratio} 封面..."),
            run_redraw_asset(provider, p_cover, [args.style_ref], cover_size, cover_ratio, str(out_dir / cover_file)),
        )))

    if "character" in steps:
        p_char = (
            f"Waist-up character illustration for a paper pop-up {card_theme_en} card standee. "
            f"Preserve the exact facial likeness, warm expression, hairstyle, clothing, and hand pose of the person in Image 2: {portrait_desc}. "
            f"Completely re-illustrate the figure in the exact artistic medium and palette of Image 1 ({art_medium}). "
            f"Center with generous white space on all sides, tucking the bottom waist smoothly into a compact curved floral cluster of {motifs}. "
            f"Pure flat solid white background (#FFFFFF), zero drop shadows, zero text, zero corner specks, crisp outline for die-cutting. "
            f"{AESTHETIC_GUARD_EN}"
        )
        batch1.append(("中央人物", lambda: (
            print("[3/6] 正在按封面画风重绘中央真人立体人物（pure #FFFFFF 白底）..."),
            run_redraw_asset(provider, p_char, [args.style_ref, args.portrait], "960*1280", "3:4", str(out_dir / "character_raw.png")),
        )))

    run_parallel_batch("第 1 批（封面+人物）", batch1)

    cover_for_context = (
        str(out_dir / "cover_vertical_raw.png")
        if vertical and (out_dir / "cover_vertical_raw.png").is_file()
        else (str(out_dir / "cover_raw.png") if (out_dir / "cover_raw.png").is_file() else args.style_ref)
    )

    # ==================== 第 2 批并行：内页 + 花环拱门 + 节日道具（均依赖新封面） ====================
    batch2: List[Tuple[str, Any]] = []
    if "inside" in steps and vertical:
        shared = (
            f"Flat full-bleed horizontal landscape 4:3 paper card artwork, exact {art_medium} and palette of the attached cover. "
            f"Use {paper_tex} with edge motifs of {motifs}. No people, no cake, no Christmas tree, no lettering, no mockup. "
        )
        top_path = out_dir / "inside_top.png"

        def _gen_vertical_inside() -> None:
            # 上下内页保持原有先后衔接顺序，确保折痕色彩和景物连贯一致
            print("[4/6] 正在重绘上下翻折 4:3 长方形双页同画风连续内页（上页 -> 下页衔接）...")
            run_redraw_asset(provider, shared + (
                "Upper 4:3 page: lush decorative motifs across the top and outer left/right borders, faint distant scenery and soft pathway leading cleanly to the bottom fold edge. "
                + AESTHETIC_GUARD_EN
            ), [cover_for_context], "1280*960", "4:3", str(top_path))
            run_redraw_asset(provider, shared + (
                "Lower 4:3 page: continue the pale watercolour landscape seamlessly across the top fold edge, with a calm path through the center and richer foliage near left, right, and bottom edges. "
                "Match the paper colour of the supplied upper page so pop-up figures stand out clearly. "
                + AESTHETIC_GUARD_EN
            ), [cover_for_context, str(top_path)], "1280*960", "4:3", str(out_dir / "inside_bottom.png"))

        batch2.append(("上下双页内页", _gen_vertical_inside))
    elif "inside" in steps:
        p_inside = (
            f"Wide 3:2 flat greeting card inside spread strictly matching the artistic style ({art_medium}) of the attached card cover. "
            f"Frame the outer edges with motifs of {motifs}. "
            f"Paint a continuous low-contrast scene across the centre with distant shrubs, delicate sprigs and a curving path on {paper_tex}; show pale scenery in the spaces to either side of the figures. "
            f"No people, no cake, no Christmas tree, no text, straight-on flat view. {AESTHETIC_GUARD_EN}"
        )
        batch2.append(("横版内页", lambda: (
            print("[4/6] 正在重绘同画风 3:2 展开内页底图..."),
            run_redraw_asset(provider, p_inside, [cover_for_context], "1280*854", "3:2", str(out_dir / "inside_raw.png")),
        )))

    if "arch" in steps:
        ornament_en = "two festive vintage Christmas baubles" if is_christmas else "two festive balloons"
        p_arch = (
            f"Semicircular botanical pop-up {card_theme_en} archway standee in the exact {art_medium} style. "
            f"Composed of {motifs}, arched festive lettering reading '{greeting_upper}' along the top curve, and {ornament_en} at the top-right shoulder. "
            f"Finish both feet with flat lower edges on one level horizontal baseline. Their outer edges define the full width of the arch. "
            f"Pure flat solid white background (#FFFFFF) including open space below the arch, zero shadows, zero corner specks. {AESTHETIC_GUARD_EN}"
        )
        batch2.append(("花环拱门", lambda: (
            print(f"[5/6] 正在重绘同画风后景花环拱门立牌《{greeting_upper}》..."),
            run_redraw_asset(provider, p_arch, [cover_for_context], "1280*960", "4:3", str(out_dir / "arch_raw.png")),
        )))

    if steps.intersection({"prop", "cake", "tree"}):
        if is_christmas:
            p_tree = (
                f"Hand-painted {art_medium} pop-up paper standee of a charming lush miniature Christmas tree in a rustic wooden planter pot "
                f"harmonious with the card palette. Decorate the pine branches with vintage ornaments, berries, tiny ribbons, and a delicate hand-painted gold star topper. "
                f"Show a flat level base at the bottom of the pot. Pure flat solid white background (#FFFFFF), clean narrow margins, zero drop shadows, zero text, zero corner specks. "
                f"{AESTHETIC_GUARD_EN}"
            )
            batch2.append(("立体圣诞树", lambda: (
                print("[6/6] 正在重绘同画风左前立体手绘圣诞树立牌..."),
                run_redraw_asset(provider, p_tree, [cover_for_context], "960*1280", "3:4", str(out_dir / "tree_raw.png")),
            )))
        else:
            p_cake = (
                f"Hand-painted {art_medium} pop-up paper standee of a rustic wooden garden table and chair holding a two-tier frosted birthday cake "
                f"harmonious with the card palette. Place ONE centered upright striped candle on the very top ending in a short unlit dark wick. "
                f"Keep the arrangement compact, with the chair tucked beside the table. Show every foot, with the lowest feet on a common baseline. "
                f"CRITICAL: NO fire, NO flame, NO glow on the candle. Pure flat solid white background (#FFFFFF), clean narrow margins, zero shadows, zero text, zero corner specks. "
                f"{AESTHETIC_GUARD_EN}"
            )
            batch2.append(("蛋糕桌椅", lambda: (
                print("[6/6] 正在重绘同画风左前木桌双层蛋糕..."),
                run_redraw_asset(provider, p_cake, [cover_for_context], "960*1280", "3:4", str(out_dir / "cake_raw.png")),
            )))

    run_parallel_batch("第 2 批（内页+拱门+道具）", batch2)

    print(f"[OK] 全套 AI 重绘素材已完成，输出目录: {out_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
