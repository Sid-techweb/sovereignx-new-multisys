"""
Tests for the scanned-PDF -> local vision OCR fallback (app/services/
extractors.py PDFExtractor). The vision model call itself is mocked (Qwen2-VL
is expensive to load and its actual output quality was already verified
through the multimodal image-upload path); what's under test here is the
FALLBACK WIRING -- does a genuinely text-layer-free PDF correctly trigger
rasterization + per-page vision calls with the right mode, does a normal
text PDF correctly skip the fallback entirely, and is the page cap honored.

Test PDFs are built with real PyMuPDF (fitz), not fixtures on disk --
a "scanned" PDF here is a real PDF containing only a rendered image per
page and no text layer, which is the exact condition pypdf.extract_text()
returns empty for.
"""
import io
import unittest
from unittest.mock import patch

import fitz
from PIL import Image


def _make_text_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"This is real embedded text on page {i + 1}.")
    data = doc.tobytes()
    doc.close()
    return data


def _make_scanned_pdf(pages: int = 1) -> bytes:
    """A PDF with no text layer at all -- each page is just an embedded
    raster image, exactly like a photographed/scanned document."""
    doc = fitz.open()
    for i in range(pages):
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page = doc.new_page()
        page.insert_image(fitz.Rect(0, 0, 200, 100), stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


class TestScannedPdfFallback(unittest.TestCase):
    def test_normal_text_pdf_never_triggers_vision_fallback(self):
        from app.services.extractors import PDFExtractor
        pdf_bytes = _make_text_pdf(pages=2)

        with patch("app.services.extractors.ImageExtractor.extract") as mock_extract:
            extractor = PDFExtractor()
            text, meta = extractor.extract(pdf_bytes, filename="normal.pdf")

        mock_extract.assert_not_called()
        self.assertIn("page 1", text)
        self.assertIn("page 2", text)
        self.assertNotIn("extraction_method", meta)

    def test_scanned_pdf_triggers_vision_fallback_with_correct_mode(self):
        from app.services.extractors import PDFExtractor
        pdf_bytes = _make_scanned_pdf(pages=2)

        with patch("app.services.extractors.ImageExtractor.extract") as mock_extract:
            mock_extract.side_effect = [
                ("Transcribed text from page one.", {}),
                ("Transcribed text from page two.", {}),
            ]
            extractor = PDFExtractor()
            text, meta = extractor.extract(pdf_bytes, filename="scanned_report.pdf")

        self.assertEqual(mock_extract.call_count, 2)
        for call in mock_extract.call_args_list:
            self.assertEqual(call.kwargs.get("mode_hint"), "scanned_document_ocr")
        self.assertIn("Transcribed text from page one.", text)
        self.assertIn("Transcribed text from page two.", text)
        self.assertEqual(meta["extraction_method"], "vision_ocr_fallback")
        self.assertEqual(meta["vision_pages_processed"], 2)
        self.assertFalse(meta["vision_pages_truncated"])

    def test_page_count_is_capped_and_truncation_reported(self):
        from app.services.extractors import PDFExtractor, MAX_VISION_FALLBACK_PAGES
        pdf_bytes = _make_scanned_pdf(pages=MAX_VISION_FALLBACK_PAGES + 3)

        with patch("app.services.extractors.ImageExtractor.extract") as mock_extract:
            mock_extract.return_value = ("page text", {})
            extractor = PDFExtractor()
            text, meta = extractor.extract(pdf_bytes, filename="long_scanned.pdf")

        self.assertEqual(mock_extract.call_count, MAX_VISION_FALLBACK_PAGES)
        self.assertEqual(meta["vision_pages_processed"], MAX_VISION_FALLBACK_PAGES)
        self.assertTrue(meta["vision_pages_truncated"])
        self.assertEqual(meta["page_count"], MAX_VISION_FALLBACK_PAGES + 3)

    def test_per_page_vision_failure_does_not_abort_the_whole_document(self):
        from app.services.extractors import PDFExtractor, ExtractionError
        pdf_bytes = _make_scanned_pdf(pages=2)

        with patch("app.services.extractors.ImageExtractor.extract") as mock_extract:
            mock_extract.side_effect = [
                ExtractionError("simulated model failure on page 1"),
                ("page two transcribed fine", {}),
            ]
            extractor = PDFExtractor()
            text, meta = extractor.extract(pdf_bytes, filename="partial_fail.pdf")

        self.assertNotIn("simulated model failure", text)
        self.assertIn("page two transcribed fine", text)

    def test_mode_hint_selects_ocr_prompt_over_filename_heuristic(self):
        """A rasterized PDF page's filename is the ORIGINAL pdf's name (e.g.
        'inspection.pdf'), which has no diagram/photo keywords -- mode_hint
        must still route to scanned_document_ocr rather than the default
        equipment-captioning prompt."""
        from app.services.extractors import ImageExtractor
        from unittest.mock import MagicMock
        import app.services.extractors as extractors_module

        img = Image.new("RGB", (50, 50), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        fake_model = MagicMock()
        fake_processor = MagicMock()
        fake_processor.apply_chat_template.return_value = "prompt text"
        fake_processor.batch_decode.return_value = ["transcribed"]

        with patch.object(ImageExtractor, "_initialize_model"):
            with patch.object(extractors_module, "torch") as mock_torch:
                mock_torch.no_grad.return_value.__enter__ = lambda self: None
                mock_torch.no_grad.return_value.__exit__ = lambda self, *a: None
                with patch("qwen_vl_utils.process_vision_info", return_value=([], [])):
                    extractor = ImageExtractor()
                    extractor._model = fake_model
                    extractor._model.parameters.return_value = iter([MagicMock(device="cpu")])
                    extractor._model.generate.return_value = [MagicMock()]
                    extractor._processor = fake_processor
                    fake_processor.return_value = {"input_ids": [[]]}

                    extractor.extract(buf.getvalue(), filename="inspection_report.pdf", mode_hint="scanned_document_ocr")

        # The captured prompt sent to apply_chat_template must be the OCR prompt.
        called_messages = fake_processor.apply_chat_template.call_args[0][0]
        prompt_text = called_messages[0]["content"][1]["text"]
        self.assertIn("Perform OCR", prompt_text)
        self.assertIn("Transcribe", prompt_text)


if __name__ == "__main__":
    unittest.main()
