"""Unit tests for WhatsApp Image & Vision Pipeline."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from media.image_handler import ImageHandler


def test_process_image_content_blocks():
    handler = ImageHandler()
    dummy_bytes = b"fake-jpeg-binary-image-data-12345"
    caption = "How much would an app like this cost?"

    res = handler.process_image(dummy_bytes, mimetype="image/jpeg", caption=caption)
    assert "content_blocks" in res
    assert len(res["content_blocks"]) == 2

    img_block = res["content_blocks"][0]
    txt_block = res["content_blocks"][1]

    assert img_block["type"] == "image"
    assert img_block["source"]["type"] == "base64"
    assert img_block["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(img_block["source"]["data"]) == dummy_bytes

    assert txt_block["type"] == "text"
    assert txt_block["text"] == caption


def test_process_image_default_prompt_when_no_caption():
    handler = ImageHandler()
    dummy_bytes = b"sample-invoice-bytes"

    res = handler.process_image(dummy_bytes, mimetype="image/png", caption="")
    img_block = res["content_blocks"][0]
    txt_block = res["content_blocks"][1]

    assert img_block["source"]["media_type"] == "image/png"
    assert "OCR" in txt_block["text"]
    assert "receipts, invoices" in txt_block["text"]


def test_process_image_unsupported_mime_defaults_to_jpeg():
    handler = ImageHandler()
    dummy_bytes = b"raw-bytes"

    res = handler.process_image(dummy_bytes, mimetype="image/tiff", caption="Check this")
    img_block = res["content_blocks"][0]
    assert img_block["source"]["media_type"] == "image/jpeg"
