from __future__ import annotations

from transformers import DataCollatorForLanguageModeling


def build_collator(tokenizer):
    return DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
