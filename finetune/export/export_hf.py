from __future__ import annotations

import argparse

from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Export model/tokenizer to HF-compatible directory.")
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--output_path", required=True)
    args = parser.parse_args()

    model = AutoModelForCausalLM.from_pretrained(args.model_path, trust_remote_code=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    model.save_pretrained(args.output_path)
    tokenizer.save_pretrained(args.output_path)
    print(f"[export] hf artifacts -> {args.output_path}")


if __name__ == "__main__":
    main()
