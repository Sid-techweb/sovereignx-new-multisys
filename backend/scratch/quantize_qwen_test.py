import os
import sys
import torch
from unittest.mock import patch
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

def main():
    print("Testing Qwen2-VL 4-bit quantized model loading...")
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
    
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4"
    )
    
    print("Mocking torch.cuda.is_available = True...")
    with patch("torch.cuda.is_available", return_value=True):
        try:
            cls_processor = AutoProcessor.from_pretrained(
                "Qwen/Qwen2-VL-2B-Instruct",
                local_files_only=True
            )
            print("Processor loaded successfully.")
            
            print("Loading 4-bit model...")
            cls_model = Qwen2VLForConditionalGeneration.from_pretrained(
                "Qwen/Qwen2-VL-2B-Instruct",
                quantization_config=quantization_config,
                device_map="auto",
                local_files_only=True
            )
            print("Model loaded successfully!")
        except Exception as e:
            print("Failed to load quantized model:")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
