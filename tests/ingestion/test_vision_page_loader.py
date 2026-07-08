from pathlib import Path

from app.ingestion.loaders import vision_page_loader as loader


async def test_load_or_ocr_page_ghi_cache_lan_dau(mocker, tmp_path):
    ocr = mocker.patch.object(
        loader, "ocr_page_image", mocker.AsyncMock(return_value="# Bài 1: TẬP HỢP")
    )
    image = tmp_path / "6.png"
    image.write_bytes(b"fake-png")
    cache = tmp_path / "cache" / "6.md"

    md = await loader.load_or_ocr_page(image, cache)

    assert md == "# Bài 1: TẬP HỢP"
    assert cache.read_text(encoding="utf-8") == "# Bài 1: TẬP HỢP"
    ocr.assert_awaited_once()


async def test_load_or_ocr_page_dung_cache_khong_goi_lai_llm(mocker, tmp_path):
    ocr = mocker.patch.object(loader, "ocr_page_image", mocker.AsyncMock(return_value="MỚI"))
    image = tmp_path / "6.png"
    image.write_bytes(b"fake-png")
    cache = tmp_path / "6.md"
    cache.write_text("ĐÃ CACHE", encoding="utf-8")

    md = await loader.load_or_ocr_page(image, cache)

    assert md == "ĐÃ CACHE"  # đọc cache, không OCR lại
    ocr.assert_not_awaited()


async def test_load_or_ocr_page_force_bo_qua_cache(mocker, tmp_path):
    mocker.patch.object(loader, "ocr_page_image", mocker.AsyncMock(return_value="OCR LẠI"))
    image = tmp_path / "6.png"
    image.write_bytes(b"fake-png")
    cache = tmp_path / "6.md"
    cache.write_text("CŨ", encoding="utf-8")

    md = await loader.load_or_ocr_page(image, cache, force=True)

    assert md == "OCR LẠI"
    assert cache.read_text(encoding="utf-8") == "OCR LẠI"
