import os
import time
import requests
import base64
from typing import Optional
from rich.console import Console

console = Console()

def generate_and_save_image(prompt: str, output_path: str, aspect_ratio: str = "3:4", max_retries: int = 2) -> bool:
    """
    使用 Nano Banana 2 (Gemini 3.1 Flash Image) 模型的 generateContent API 生成图片并保存。
    aspect_ratio: "1:1", "3:4" (小红书首选), "4:3", "16:9" 等
    """
    from src.api_router import keys_manager

    enriched_prompt = f"{prompt}, high quality, highly detailed, visually appealing, modern style"
    model = "gemini-3.1-flash-image-preview"

    def _do_generate(api_key: str):
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": enriched_prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        
        # 抛出异常由 keys_manager 去判定是否需要换 key
        response.raise_for_status()
        body = response.json()

        candidates = body.get("candidates", [])
        for candidate in candidates:
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if not inline_data:
                    continue
                data = inline_data.get("data")
                mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
                if data and str(mime_type).startswith("image/"):
                    image_bytes = base64.b64decode(data)
                    with open(output_path, "wb") as f:
                        f.write(image_bytes)
                    return True
        
        error_msg = body.get("error", {}).get("message", "Unknown error or no image payload returned")
        raise RuntimeError(f"未返回图片数据: {error_msg}")

    try:
        # 使用容灾控制器发起调用，最多对每个 key 重试 2 次
        return keys_manager.execute_with_fallback(
            provider="gemini",
            max_retries_per_key=max_retries,
            task_func=_do_generate
        )
    except Exception as e:
        console.print(f"  [red]Nano Banana 2 生图彻底失败: {e}[/red]")
        return False
