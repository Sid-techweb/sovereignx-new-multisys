import csv
import io
import logging
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import torch
from PIL import Image

logger = logging.getLogger("sovereignx")

import re

class ExtractionError(Exception):
    """Base exception for extraction failures."""
    pass

def strip_conversational_preamble(text: str) -> str:
    # Remove leading common conversational preambles
    prefixes = [
        r"^Certainly!\s*Here is the extracted text.*?:\s*",
        r"^Certainly!\s*Here are the extracted.*?:\s*",
        r"^Certainly!\s*Here is the description.*?:\s*",
        r"^Certainly!\s*Here are the details.*?:\s*",
        r"^Certainly!\s*Here is the.*?:\s*",
        r"^Certainly,\s*here is.*?:\s*",
        r"^Certainly,\s*here are.*?:\s*",
        r"^Here is the extracted text.*?:\s*",
        r"^Here is the description.*?:\s*",
        r"^Here is the P&ID.*?:\s*",
        r"^Here is the image.*?:\s*",
        r"^Based on the image.*?:\s*",
        r"^Based on the P&ID.*?:\s*",
        r"^Sure!?\s*Here is.*?:\s*",
        r"^Sure!?\s*Here are.*?:\s*"
    ]
    
    cleaned = text
    for prefix in prefixes:
        cleaned_temp = re.sub(prefix, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if cleaned_temp != cleaned:
            cleaned = cleaned_temp
            break
            
    # Also strip any leading separator like "---" or "---\n"
    cleaned = cleaned.strip()
    if cleaned.startswith("---"):
        cleaned = re.sub(r"^---+\s*", "", cleaned).strip()
    return cleaned

class DocumentExtractor(ABC):
    @abstractmethod
    def extract(self, file_content: bytes, filename: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts content and format-specific metadata from document content.
        
        Args:
            file_content: Binary contents of the document.
            filename: Optional filename of the document for format-specific routing.
            
        Returns:
            A tuple of (extracted_text, metadata_dict).
        """
        pass

class PDFExtractor(DocumentExtractor):
    def extract(self, file_content: bytes, filename: str = None) -> Tuple[str, Dict[str, Any]]:
        try:
            reader = PdfReader(io.BytesIO(file_content))
            page_count = len(reader.pages)
            
            extracted_pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    extracted_pages.append(text.strip())
            
            full_text = "\n\n---SOVEREIGNX-PAGE-BREAK---\n\n".join(extracted_pages).strip()
            
            metadata = {
                "page_count": page_count,
                "has_text": len(full_text) > 0
            }
            
            return full_text, metadata
        except PdfReadError as e:
            raise ExtractionError(f"Corrupt PDF file: {str(e)}")
        except Exception as e:
            raise ExtractionError(f"PDF extraction failed: {str(e)}")

class CSVExtractor(DocumentExtractor):
    def extract(self, file_content: bytes, filename: str = None) -> Tuple[str, Dict[str, Any]]:
        try:
            # Decode file content safely
            # Try utf-8, fallback to latin-1
            try:
                decoded = file_content.decode("utf-8")
            except UnicodeDecodeError:
                decoded = file_content.decode("latin-1")
                
            reader = csv.reader(io.StringIO(decoded))
            rows = list(reader)
            
            if not rows:
                return "", {"row_count": 0, "column_count": 0}
                
            headers = [h.strip() for h in rows[0]]
            data_rows = rows[1:]
            
            extracted_text_blocks = []
            for r_idx, row in enumerate(data_rows):
                row_fields = []
                for c_idx, val in enumerate(row):
                    if c_idx < len(headers):
                        key = headers[c_idx]
                    else:
                        key = f"Column_{c_idx + 1}"
                    row_fields.append(f"{key}: {val.strip()}")
                extracted_text_blocks.append("\n".join(row_fields))
                
            full_text = "\n\n".join(extracted_text_blocks).strip()
            
            metadata = {
                "row_count": len(data_rows),
                "column_count": len(headers),
                "headers": headers
            }
            
            return full_text, metadata
        except Exception as e:
            raise ExtractionError(f"CSV extraction failed: {str(e)}")

class ImageExtractor(DocumentExtractor):
    _model = None
    _processor = None

    @classmethod
    def _initialize_model(cls):
        if cls._model is None:
            logger.info("Initializing Qwen2-VL-2B-Instruct locally...")
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            
            cls._processor = AutoProcessor.from_pretrained(
                "Qwen/Qwen2-VL-2B-Instruct",
                local_files_only=True
            )
            
            if torch.cuda.is_available():
                try:
                    from transformers import BitsAndBytesConfig
                    quantization_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4"
                    )
                    cls._model = Qwen2VLForConditionalGeneration.from_pretrained(
                        "Qwen/Qwen2-VL-2B-Instruct",
                        quantization_config=quantization_config,
                        device_map="auto",
                        local_files_only=True
                    )
                    logger.info("Qwen2-VL loaded locally in 4-bit quantized mode to GPU (CUDA)")
                except Exception as e:
                    logger.warning(f"Failed to load Qwen2-VL in 4-bit mode: {e}. Falling back to standard load.")
                    cls._model = Qwen2VLForConditionalGeneration.from_pretrained(
                        "Qwen/Qwen2-VL-2B-Instruct",
                        local_files_only=True
                    )
                    cls._model = cls._model.to("cuda")
                    logger.info("Qwen2-VL loaded to GPU (CUDA)")
            else:
                cls._model = Qwen2VLForConditionalGeneration.from_pretrained(
                    "Qwen/Qwen2-VL-2B-Instruct",
                    local_files_only=True
                )
                cls._model = cls._model.to("cpu")
                logger.info("Qwen2-VL loaded to CPU")

    def extract(self, file_content: bytes, filename: str = None) -> Tuple[str, Dict[str, Any]]:
        try:
            self._initialize_model()
            
            # Load PIL image
            image = Image.open(io.BytesIO(file_content)).convert("RGB")
            width, height = image.size
            
            # Formulate task-oriented prompt based on filename/type
            is_diagram = False
            if filename:
                fn_lower = filename.lower()
                if any(k in fn_lower for k in ["pid", "p&id", "schematic", "diagram", "flow"]):
                    is_diagram = True
                    
            if is_diagram:
                prompt = (
                    "Perform OCR and extract all text, labels, equipment tags, valve IDs, pipe sizes, "
                    "notes, and annotations visible in this Piping and Instrumentation Diagram (P&ID). "
                    "List them clearly and thoroughly."
                )
                mode = "pid_schematic_ocr"
            else:
                prompt = (
                    "Provide a detailed visual description and caption of this equipment photo. "
                    "Describe the machinery, environment, components, and what is shown in the image."
                )
                mode = "equipment_visual_captioning"
                
            logger.info(f"Running visual extraction for {filename or 'unnamed'} in mode: {mode}")
            
            # Format inputs for model with max_pixels limits to accelerate CPU execution
            max_px = 512 * 512 if is_diagram else 256 * 256
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image, "max_pixels": max_px},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            
            from qwen_vl_utils import process_vision_info
            text_prompt = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self._processor(
                text=[text_prompt],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
            
            # Move inputs to target model device
            device = next(self._model.parameters()).device
            if not ("Mock" in type(device).__name__ or hasattr(device, "_spec_class")):
                inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
            
            # Perform inference under torch.no_grad
            with torch.no_grad():
                generated_ids = self._model.generate(**inputs, max_new_tokens=512)
                
            generated_ids_trimmed = [
                out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
            ]
            extracted_text = self._processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0].strip()
            extracted_text = strip_conversational_preamble(extracted_text)
            
            metadata = {
                "image_width": width,
                "image_height": height,
                "extraction_mode": mode,
                "device": str(device)
            }
            
            logger.info(f"Visual extraction completed for {filename or 'unnamed'}. Character count: {len(extracted_text)}")
            return extracted_text, metadata
            
        except Exception as e:
            logger.error(f"Image visual extraction failed: {str(e)}")
            raise ExtractionError(f"Image visual extraction failed: {str(e)}") from e

def get_extractor(file_extension: str) -> DocumentExtractor:
    ext = file_extension.lower().lstrip(".")
    if ext == "pdf":
        return PDFExtractor()
    elif ext == "csv":
        return CSVExtractor()
    elif ext in ["png", "jpg", "jpeg"]:
        return ImageExtractor()
    else:
        raise ValueError(f"Unsupported file extension for extraction: {file_extension}")
