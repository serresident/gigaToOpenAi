import re
from pathlib import Path
import json
import sqlite3
import winreg
import ctypes
import shutil

CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
AUTH_JSON = Path.home() / ".codex" / "auth.json"

def patch_codex():
    if not CODEX_CONFIG.exists():
        print("Config does not exist")
        return

    shutil.copy2(CODEX_CONFIG, CODEX_CONFIG.with_suffix(".toml.bak"))
    
    text = CODEX_CONFIG.read_text("utf-8")
    
    # Remove existing global keys for model and provider
    text = re.sub(r'(?m)^model\s*=.*$\n?', '', text)
    text = re.sub(r'(?m)^model_provider\s*=.*$\n?', '', text)
    text = re.sub(r'(?m)^model_reasoning_effort\s*=.*$\n?', '', text)

    top_level_insert = """model = "GigaChat-3-Ultra"
model_provider = "gpt2giga"
model_reasoning_effort = "none"

"""
    # Insert at the very beginning
    text = top_level_insert + text

    # Add gpt2giga provider block if not exists
    if "[model_providers.gpt2giga]" not in text:
        text += """
[model_providers.gpt2giga]
name = "gpt2giga"
base_url = "http://localhost:8090/v2"
env_key = "GPT2GIGA_API_KEY"
wire_api = "responses"
supports_websockets = false
"""
    
    # Also patch the profiles to use gpt2giga
    text = re.sub(r'(?m)^model_provider\s*=\s*"relaymodels"', 'model_provider = "gpt2giga"', text)
    
    CODEX_CONFIG.write_text(text, "utf-8")

    # Patch auth.json
    if AUTH_JSON.exists():
        auth = json.loads(AUTH_JSON.read_text("utf-8"))
        auth["auth_mode"] = "apikey"
        auth["OPENAI_API_KEY"] = "sk-gigachat"
        AUTH_JSON.write_text(json.dumps(auth, indent=2), "utf-8")
    
    # Environment variables
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "OPENAI_API_KEY", 0, winreg.REG_SZ, "sk-gigachat")
        winreg.SetValueEx(key, "OPENAI_BASE_URL", 0, winreg.REG_SZ, "http://localhost:8090/v2")
        winreg.SetValueEx(key, "GPT2GIGA_API_KEY", 0, winreg.REG_SZ, "sk-gigachat")
        winreg.CloseKey(key)
        
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None)
    except Exception as e:
        print(f"Env Var Error: {e}")

patch_codex()
print("Fixed config.toml and auth.json")
