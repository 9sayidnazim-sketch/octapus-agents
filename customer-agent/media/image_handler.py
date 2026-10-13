"""Image & Vision Handler for WhatsApp.

Formats image inputs as proper multimodal content blocks (base64) for vision-capable models (e.g. Claude 3.5 Sonnet).
Supports OCR, product descriptions, receipt and invoice analysis, and answering visual inquiries.
Optionally integrates with external Vision API (VISION_API_URL / VISION_API_KEY) if configured.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger("octapus.media.image")

DEFAULT_IMAGE_PROMPT = (
    "Please inspect this image and assist the user. If the image contains text (OCR), "
    "receipts, invoices, products, designs, documents, or screenshots, read and analyze them "
    "accurately. Answer any user questions or provide a concise, helpful breakdown."
)


class ImageHandler:
    def __init__(
        self,
        vision_api_url: Optional[str] = None,
        vision_api_key: Optional[str] = None,
    ):
        self.vision_url = (vision_api_url or os.environ.get("VISION_API_URL") or "").strip()
        self.vision_key = (vision_api_key or os.environ.get("VISION_API_KEY") or "").strip()

    def process_image(
        self,
        image_bytes: bytes,
        mimetype: str = "image/jpeg",
        caption: str = "",
    ) -> Dict[str, Any]:
        """
        Process an image attachment.
        Returns a dictionary with:
        - 'content_blocks': Anthropic-compatible list of content blocks [image_block, text_block]
        - 'b64_data': base64 encoded image string
        - 'mimetype': clean media_type (image/jpeg, image/png, image/webp, image/gif)
        - 'caption': user caption or default vision prompt
        """
        if not image_bytes:
            raise ValueError("Image data is empty.")

        clean_mime = mimetype.split(";")[0].strip().lower()
        if clean_mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            clean_mime = "image/jpeg"

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        user_prompt = caption.strip() if caption.strip() else DEFAULT_IMAGE_PROMPT

        # 1. If an external Vision API is configured, query it for a textual analysis
        external_analysis: Optional[str] = None
        if self.vision_url and self.vision_key:
            external_analysis = self._call_external_vision(b64_data, clean_mime, user_prompt)

        # 2. Build standard Anthropic content blocks for native multimodal processing
        image_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": clean_mime,
                "data": b64_data,
            },
        }

        prompt_text = user_prompt
        if external_analysis:
            prompt_text = f"{user_prompt}\n\n[Vision OCR / Analysis]:\n{external_analysis}"

        text_block = {
            "type": "text",
            "text": prompt_text,
        }

        return {
            "content_blocks": [image_block, text_block],
            "b64_data": b64_data,
            "mimetype": clean_mime,
            "caption": prompt_text,
            "external_analysis": external_analysis,
        }

    def _call_external_vision(self, b64_data: str, mimetype: str, prompt: str) -> Optional[str]:
        """Call external vision endpoint if explicitly configured."""
        try:
            headers = {
                "Authorization": f"Bearer {self.vision_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": os.environ.get("VISION_MODEL", "gpt-4o"),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mimetype};base64,{b64_data}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 800,
            }
            with httpx.Client(timeout=25.0) as client:
                res = client.post(self.vision_url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("External vision API call failed: %s", e)
        return None
