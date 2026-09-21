import re
from pathlib import Path
import os

# 1. Update .env
env_path = Path("c:/Users/adm/projects/gigaToOpenAi/.env")
if env_path.exists():
    text = env_path.read_text("utf-8")
    text = re.sub(r'(?m)^GPT2GIGA_DISABLE_REASONING=.*$', 'GPT2GIGA_DISABLE_REASONING=True', text)
    env_path.write_text(text, "utf-8")

# 2. Update config.toml
codex_config = Path.home() / ".codex" / "config.toml"
if codex_config.exists():
    text = codex_config.read_text("utf-8")
    text = re.sub(r'(?m)^model_reasoning_effort\s*=.*$', 'model_reasoning_effort = "none"', text)
    codex_config.write_text(text, "utf-8")

# 3. Update proxy_manager.py
proxy_manager_path = Path("c:/Users/adm/projects/gigaToOpenAi/proxy_manager.py")
if proxy_manager_path.exists():
    text = proxy_manager_path.read_text("utf-8")
    text = re.sub(r'(?m)^(\s*"GPT2GIGA_DISABLE_REASONING"\s*:\s*)"False"', r'\1"True"', text)
    text = re.sub(r'(?m)^(\s*model_reasoning_effort\s*=\s*)"high"', r'\1"none"', text)
    proxy_manager_path.write_text(text, "utf-8")

print("Done reverting reasoning settings.")
