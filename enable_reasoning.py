import re
from pathlib import Path
import os

# 1. Update .env
env_path = Path("c:/Users/adm/projects/gigaToOpenAi/.env")
if env_path.exists():
    text = env_path.read_text("utf-8")
    text = re.sub(r'(?m)^GPT2GIGA_DISABLE_REASONING=.*$', 'GPT2GIGA_DISABLE_REASONING=False', text)
    env_path.write_text(text, "utf-8")

# 2. Update config.toml
codex_config = Path.home() / ".codex" / "config.toml"
if codex_config.exists():
    text = codex_config.read_text("utf-8")
    text = re.sub(r'(?m)^model_reasoning_effort\s*=.*$', 'model_reasoning_effort = "high"', text)
    if 'model_reasoning_summary = "auto"' not in text:
        text = re.sub(r'(?m)^model_provider\s*=\s*"gpt2giga"', 'model_provider = "gpt2giga"\nmodel_reasoning_summary = "auto"\nmodel_supports_reasoning_summaries = true', text)
    codex_config.write_text(text, "utf-8")

print("Done patching.")
