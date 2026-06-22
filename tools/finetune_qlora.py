"""QLoRA fine-tune of L3-8B-Lunaris on the carved Cricket corpus (data/finetune/train.jsonl).

4-bit nf4 base + LoRA adapters, prompt-MASKED (loss only on Cricket's pose, not the ~7.5k-token
prompt), Llama-3 chat template applied via the tokenizer so train format == inference format.
Small corpus (39 examples), so low rank + few epochs to limit the canned-line overfit the design
doc warns about. Writes the adapter to data/finetune/lunaris-cricket-lora/.

  python tools/finetune_qlora.py
"""

import json
import os
import sys

import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                          TrainingArguments, Trainer)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Use the resolved local snapshot path (written by the download step) to avoid any HF lookup.
_bp = os.path.join(_ROOT, "data", "finetune", "base_path.txt")
BASE = open(_bp).read().strip() if os.path.exists(_bp) else "Sao10K/L3-8B-Lunaris-v1"
OUT = os.path.join(_ROOT, "data", "finetune", "lunaris-cricket-lora")
MAXLEN = 8192


def build_dataset(tok):
    rows = [json.loads(l) for l in open(os.path.join(_ROOT, "data", "finetune", "train.jsonl"), encoding="utf-8")]
    data = []
    for r in rows:
        msgs = r["messages"]
        full = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=False)
        prompt = tok.apply_chat_template(msgs[:-1], tokenize=True, add_generation_prompt=True)
        if len(full) > MAXLEN:                       # left-truncate the prompt, keep the completion
            cut = len(full) - MAXLEN
            full, prompt = full[cut:], prompt[max(0, len(prompt) - (MAXLEN - (len(full) - len(prompt)))):]
        labels = [-100] * len(prompt) + full[len(prompt):]  # mask the prompt; train on the pose
        labels = labels[:len(full)]
        data.append({"input_ids": full, "labels": labels})
    return data


def collate(batch, pad_id):
    m = max(len(b["input_ids"]) for b in batch)
    ids, labs, att = [], [], []
    for b in batch:
        p = m - len(b["input_ids"])
        ids.append(b["input_ids"] + [pad_id] * p)
        labs.append(b["labels"] + [-100] * p)
        att.append([1] * len(b["input_ids"]) + [0] * p)
    return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labs),
            "attention_mask": torch.tensor(att)}


def main():
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    data = build_dataset(tok)
    print("examples=%d  token lengths: median=%d max=%d"
          % (len(data), sorted(len(d["input_ids"]) for d in data)[len(data) // 2],
             max(len(d["input_ids"]) for d in data)))
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb,
                                                 torch_dtype=torch.bfloat16, device_map="auto")
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    args = TrainingArguments(
        output_dir=OUT, num_train_epochs=3, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, learning_rate=2e-4, lr_scheduler_type="cosine",
        warmup_ratio=0.05, bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1, save_strategy="epoch", report_to=[], optim="paged_adamw_8bit")
    Trainer(model=model, args=args, train_dataset=data,
            data_collator=lambda b: collate(b, tok.pad_token_id)).train()
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print("saved adapter ->", OUT)


if __name__ == "__main__":
    main()
