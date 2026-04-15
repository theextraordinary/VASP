from __future__ import annotations

import argparse

from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model.")
    parser.add_argument("--base_model", required=True)
    parser.add_argument("--adapter_path", required=True)
    parser.add_argument("--output_path", required=True)
    args = parser.parse_args()

    base = AutoModelForCausalLM.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer = AutoTokenizer.from_pretrained(args.adapter_path, trust_remote_code=True)

    peft_model = PeftModel.from_pretrained(base, args.adapter_path)
    merged = peft_model.merge_and_unload()
    merged.save_pretrained(args.output_path)
    tokenizer.save_pretrained(args.output_path)
    print(f"[export] merged model -> {args.output_path}")


if __name__ == "__main__":
    main()
