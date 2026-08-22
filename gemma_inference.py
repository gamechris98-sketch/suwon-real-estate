import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = os.getenv("GEMMA_MODEL", "google/gemma-2b-it")

# Determine device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Load once
_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
_model.to(DEVICE)
_model.eval()

def generate(prompt: str, max_new_tokens: int = 256) -> str:
    """Generate a response from the Gemma model.
    Args:
        prompt: Input text.
        max_new_tokens: Number of tokens to generate.
    Returns:
        Generated text (str) without special tokens.
    """
    inputs = _tokenizer(prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.7)
    return _tokenizer.decode(outputs[0], skip_special_tokens=True)
