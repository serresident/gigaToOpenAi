import sys
import os
import shutil
import json
import uuid
import requests
import subprocess
import sqlite3
import winreg
import ctypes
import urllib3
import yaml
import webbrowser
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGroupBox, QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

# Paths
ENV_PATH = Path(".env")
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CONTINUE_CONFIG = Path.home() / ".continue" / "config.yaml"
AGY_CLI_CONFIG = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
AGY_IDE_CONFIG = Path(os.getenv("APPDATA", "")) / "Antigravity" / "User" / "settings.json"
VSCODE_CONFIG = Path(os.getenv("APPDATA", "")) / "Code" / "User" / "settings.json"


def kill_port_zombies(port=8090):
    """Find and kill any processes listening on or holding the specified port."""
    killed = []
    if os.name == 'nt':
        try:
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0] == "TCP":
                    local_addr = parts[1]
                    state = parts[3]
                    pid_str = parts[4]
                    if f":{port}" in local_addr and state.upper().startswith("LISTEN"):
                        try:
                            pid = int(pid_str)
                            if pid > 0 and pid != os.getpid():
                                subprocess.run(
                                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW
                                )
                                killed.append(pid)
                        except ValueError:
                            pass
        except Exception:
            pass

        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "gpt2giga.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass
    return killed


class ProcessThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, command):
        super().__init__()
        self.command = command
        self.process = None

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            for line in iter(self.process.stdout.readline, ''):
                self.output_signal.emit(line.strip())
        except Exception as e:
            self.output_signal.emit(f"Error starting server: {e}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        if self.process:
            pid = self.process.pid
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                pass


class TestConnectionThread(QThread):
    log_signal = pyqtSignal(str)
    success_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str, str)

    def __init__(self, creds):
        super().__init__()
        self.creds = creds

    def run(self):
        try:
            url_oauth = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
            payload = {'scope': 'GIGACHAT_API_PERS'}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'RqUID': str(uuid.uuid4()),
                'Authorization': f'Basic {self.creds}'
            }
            self.log_signal.emit("Requesting Access Token...")
            response = requests.post(url_oauth, headers=headers, data=payload, verify=False, timeout=10)
            
            if response.status_code != 200:
                self.log_signal.emit(f"Auth Error: {response.status_code} - {response.text}")
                self.error_signal.emit("Auth Error", f"Failed to get token.\nStatus: {response.status_code}\nResponse: {response.text}")
                return
            
            token_data = response.json()
            access_token = token_data.get('access_token')
            self.log_signal.emit("Successfully obtained Access Token!")
            
            url_models = "https://api.giga.chat/v1/models"
            headers_models = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }
            self.log_signal.emit("Fetching available models...")
            resp_models = requests.get(url_models, headers=headers_models, verify=False, timeout=10)
            
            if resp_models.status_code == 200:
                models_data = resp_models.json()
                model_names = [m['id'] for m in models_data.get('data', [])]
                self.log_signal.emit(f"Available models: {', '.join(model_names)}")
                self.success_signal.emit(model_names)
            else:
                self.log_signal.emit(f"Models Error: {resp_models.status_code} - {resp_models.text}")
                self.error_signal.emit("Models Error", f"Failed to fetch models.\nStatus: {resp_models.status_code}\nResponse: {resp_models.text}")
                
        except Exception as e:
            self.log_signal.emit(f"Connection Test Exception: {str(e)}")
            self.error_signal.emit("Error", f"Exception during test:\n{str(e)}")


class ProxyManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GigaChat Proxy Manager (gpt2giga)")
        self.resize(750, 750)
        
        self.server_thread = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Settings Group ---
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        
        # Credentials Layout
        creds_layout = QHBoxLayout()
        creds_layout.addWidget(QLabel("GigaChat Credentials (API Key):"))
        self.creds_input = QLineEdit()
        self.creds_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        creds_layout.addWidget(self.creds_input)
        
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        creds_layout.addWidget(self.test_btn)
        settings_layout.addLayout(creds_layout)
        
        # Model Selection Layout
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Target GigaChat Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["GigaChat-3-Ultra", "GigaChat-Max", "GigaChat-Pro", "GigaChat-Lite"])
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        settings_layout.addLayout(model_layout)

        # Connection info
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Proxy URL (for clients):"))
        self.url_input = QLineEdit("http://localhost:8090/v2")
        self.url_input.setReadOnly(True)
        conn_layout.addWidget(self.url_input)
        settings_layout.addLayout(conn_layout)

        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("GPT2GIGA_API_KEY:"))
        self.key_input = QLineEdit("sk-gigachat")
        self.key_input.setReadOnly(True)
        key_layout.addWidget(self.key_input)
        settings_layout.addLayout(key_layout)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        self.load_env()

        # --- Control Group ---
        control_group = QGroupBox("Server Controls")
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Server")
        self.start_btn.clicked.connect(self.start_server)
        control_layout.addWidget(self.start_btn)

        self.restart_btn = QPushButton("Restart Server")
        self.restart_btn.clicked.connect(self.restart_server)
        control_layout.addWidget(self.restart_btn)
        
        self.stop_btn = QPushButton("Stop Server")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_server)
        control_layout.addWidget(self.stop_btn)

        self.kill_btn = QPushButton("Kill Zombies (Free 8090)")
        self.kill_btn.setStyleSheet("color: #d9534f; font-weight: bold;")
        self.kill_btn.clicked.connect(self.kill_zombies_manual)
        control_layout.addWidget(self.kill_btn)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # --- Patch Group ---
        patch_group = QGroupBox("Patch & Backup Configs")
        patch_layout = QVBoxLayout()
        
        # Continue (config.yaml)
        continue_layout = QHBoxLayout()
        btn_install_continue = QPushButton("🌐 Install Continue.dev")
        btn_install_continue.setToolTip("Install Continue.dev extension in VS Code or open Marketplace")
        btn_install_continue.clicked.connect(self.install_continue)
        continue_layout.addWidget(btn_install_continue)

        btn_patch_continue = QPushButton("⚙️ Patch Continue.dev")
        btn_patch_continue.setToolTip("Configure ~/.continue/config.yaml for local GigaChat server")
        btn_patch_continue.clicked.connect(self.patch_continue)
        continue_layout.addWidget(btn_patch_continue)

        btn_restore_continue = QPushButton("↩️ Restore Continue")
        btn_restore_continue.clicked.connect(lambda: self.restore_backup(CONTINUE_CONFIG))
        continue_layout.addWidget(btn_restore_continue)
        patch_layout.addLayout(continue_layout)

        # Codex
        codex_layout = QHBoxLayout()
        btn_patch_codex = QPushButton("Patch Codex")
        btn_patch_codex.clicked.connect(self.patch_codex)
        codex_layout.addWidget(btn_patch_codex)
        btn_restore_codex = QPushButton("Restore Codex")
        btn_restore_codex.clicked.connect(lambda: self.restore_backup(CODEX_CONFIG))
        codex_layout.addWidget(btn_restore_codex)
        patch_layout.addLayout(codex_layout)
        
        # AGY CLI
        agy_cli_layout = QHBoxLayout()
        btn_patch_agy_cli = QPushButton("Patch AGY CLI")
        btn_patch_agy_cli.clicked.connect(lambda: self.patch_json_config(AGY_CLI_CONFIG, "AGY CLI"))
        agy_cli_layout.addWidget(btn_patch_agy_cli)
        btn_restore_agy_cli = QPushButton("Restore AGY CLI")
        btn_restore_agy_cli.clicked.connect(lambda: self.restore_backup(AGY_CLI_CONFIG))
        agy_cli_layout.addWidget(btn_restore_agy_cli)
        patch_layout.addLayout(agy_cli_layout)

        # AGY IDE
        agy_ide_layout = QHBoxLayout()
        btn_patch_agy_ide = QPushButton("Patch AGY IDE")
        btn_patch_agy_ide.clicked.connect(lambda: self.patch_json_config(AGY_IDE_CONFIG, "AGY IDE"))
        agy_ide_layout.addWidget(btn_patch_agy_ide)
        btn_restore_agy_ide = QPushButton("Restore AGY IDE")
        btn_restore_agy_ide.clicked.connect(lambda: self.restore_backup(AGY_IDE_CONFIG))
        agy_ide_layout.addWidget(btn_restore_agy_ide)
        patch_layout.addLayout(agy_ide_layout)

        # VS Code settings
        vscode_layout = QHBoxLayout()
        btn_patch_vscode = QPushButton("Patch VS Code (settings.json)")
        btn_patch_vscode.clicked.connect(lambda: self.patch_vscode_config())
        vscode_layout.addWidget(btn_patch_vscode)
        btn_restore_vscode = QPushButton("Restore VS Code")
        btn_restore_vscode.clicked.connect(lambda: self.restore_backup(VSCODE_CONFIG))
        vscode_layout.addWidget(btn_restore_vscode)
        patch_layout.addLayout(vscode_layout)

        # VS Code Extension JS Patch
        vscode_ext_layout = QHBoxLayout()
        btn_patch_vscode_ext = QPushButton("Patch VS Code Codex Extension (JS)")
        btn_patch_vscode_ext.clicked.connect(self.patch_vscode_extension)
        vscode_ext_layout.addWidget(btn_patch_vscode_ext)
        patch_layout.addLayout(vscode_ext_layout)

        patch_group.setLayout(patch_layout)
        main_layout.addWidget(patch_group)

        # --- Logs Group ---
        log_group = QGroupBox("Server Logs")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: black; color: lightgreen; font-family: Consolas;")
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

    def load_env(self):
        if ENV_PATH.exists():
            content = ENV_PATH.read_text('utf-8')
            for line in content.splitlines():
                if line.startswith("GIGACHAT_CREDENTIALS="):
                    self.creds_input.setText(line.split("=", 1)[1].strip())
                elif line.startswith("GIGACHAT_MODEL="):
                    model = line.split("=", 1)[1].strip()
                    index = self.model_combo.findText(model)
                    if index >= 0:
                        self.model_combo.setCurrentIndex(index)
                    else:
                        self.model_combo.addItem(model)
                        self.model_combo.setCurrentText(model)
                    
    def save_env(self):
        lines = []
        if ENV_PATH.exists():
            lines = ENV_PATH.read_text('utf-8').splitlines()
        
        new_creds = self.creds_input.text().strip()
        new_model = self.model_combo.currentText().strip()
        
        creds_updated = False
        model_updated = False
        
        for i, line in enumerate(lines):
            if line.startswith("GIGACHAT_CREDENTIALS="):
                lines[i] = f"GIGACHAT_CREDENTIALS={new_creds}"
                creds_updated = True
            elif line.startswith("GIGACHAT_MODEL="):
                lines[i] = f"GIGACHAT_MODEL={new_model}"
                model_updated = True
                
        if not creds_updated:
            lines.append(f"GIGACHAT_CREDENTIALS={new_creds}")
        if not model_updated:
            lines.append(f"GIGACHAT_MODEL={new_model}")
            
        defaults = {
            "GIGACHAT_SCOPE": "GIGACHAT_API_PERS",
            "GIGACHAT_VERIFY_SSL_CERTS": "False",
            "GIGACHAT_MAX_RETRIES": "5",
            "GIGACHAT_RETRY_BACKOFF_FACTOR": "1.0",
            "GIGACHAT_TIMEOUT": "60.0",
            "GPT2GIGA_ENABLE_API_KEY_AUTH": "True",
            "GPT2GIGA_API_KEY": "sk-gigachat",
            "GPT2GIGA_GIGACHAT_API_MODE": "v2",
            "GPT2GIGA_PASS_MODEL": "False",
            "GPT2GIGA_DISABLE_REASONING": "True",
            "GPT2GIGA_MODEL_MAX_CONNECTIONS_DEFAULT": "1",
            "GPT2GIGA_MODEL_MAX_CONNECTIONS_ACQUIRE_TIMEOUT": "60.0"
        }
        
        for k, v in defaults.items():
            if not any(line.startswith(f"{k}=") for line in lines):
                lines.append(f"{k}={v}")
                
        ENV_PATH.write_text("\n".join(lines), 'utf-8')

    def log(self, msg):
        self.log_text.append(msg)

    def start_server(self):
        if not self.creds_input.text().strip():
            QMessageBox.critical(self, "Error", "Please enter GigaChat Credentials!")
            return
            
        self.save_env()
        
        # Proactively clean up any zombie process on port 8090
        killed = kill_port_zombies(8090)
        if killed:
            self.log(f"Freed port 8090 (terminated zombie PID(s): {', '.join(map(str, killed))})")
        
        python_dir = os.path.dirname(sys.executable)
        gpt2giga_path = os.path.join(python_dir, "Scripts", "gpt2giga.exe")
        
        if not os.path.exists(gpt2giga_path):
            gpt2giga_path = "gpt2giga"

        self.start_btn.setEnabled(False)
        self.restart_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        
        selected_model = self.model_combo.currentText()
        self.log(f"Started gpt2giga server (Model: {selected_model})...")

        self.server_thread = ProcessThread([gpt2giga_path])
        self.server_thread.output_signal.connect(self.log)
        self.server_thread.finished_signal.connect(self.on_process_exit)
        self.server_thread.start()

    def stop_server(self):
        self.log("Stopping server...")
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
        # Clean up any lingering process on port 8090
        kill_port_zombies(8090)
        self.on_process_exit()

    def restart_server(self):
        self.log("Restarting server...")
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
        kill_port_zombies(8090)
        self.start_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        QTimer.singleShot(1200, self.start_server)

    def kill_zombies_manual(self):
        killed = kill_port_zombies(8090)
        if killed:
            self.log(f"Cleaned up zombie process(es) holding port 8090: {', '.join(map(str, killed))}")
            QMessageBox.information(self, "Port 8090 Freed", f"Freed port 8090!\nTerminated zombie process(es): {', '.join(map(str, killed))}")
        else:
            self.log("Port 8090 is clean. No zombie processes detected.")
            QMessageBox.information(self, "Port 8090 Clean", "Port 8090 is free. No zombie processes detected.")

    def on_process_exit(self):
        self.start_btn.setEnabled(True)
        self.restart_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    def install_continue(self):
        url_vscode = "vscode:extension/Continue.continue"
        url_market = "https://marketplace.visualstudio.com/items?itemName=Continue.continue"
        self.log(f"Installing Continue.dev extension...")
        
        installed_via_cli = False
        try:
            res = subprocess.run(
                ["code", "--install-extension", "Continue.continue"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=15
            )
            if res.returncode == 0:
                installed_via_cli = True
                self.log("Successfully installed Continue.dev via VS Code CLI ('code --install-extension')!")
                QMessageBox.information(
                    self,
                    "Extension Installed",
                    "Successfully installed Continue.dev in VS Code!\n\nNow click 'Patch Continue.dev' to configure GigaChat models."
                )
                return
        except Exception:
            pass

        # Fallback to opening VS Code URL and Marketplace webpage
        try:
            webbrowser.open(url_vscode)
        except Exception:
            pass
        try:
            webbrowser.open(url_market)
        except Exception:
            pass
            
        self.log(f"Opened Continue.dev Marketplace page: {url_market}")
        QMessageBox.information(
            self,
            "Install Continue.dev",
            f"Opened Continue.dev in VS Code and Web Browser:\n{url_market}\n\nClick 'Install' in VS Code to complete installation."
        )

    def patch_continue(self):
        selected_model = self.model_combo.currentText() or "GigaChat-3-Ultra"
        if not CONTINUE_CONFIG.parent.exists():
            CONTINUE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            
        self.make_backup(CONTINUE_CONFIG)
        
        data = {"name": "Main Config", "version": "1.0.0", "schema": "v1", "models": []}
        if CONTINUE_CONFIG.exists():
            try:
                content = CONTINUE_CONFIG.read_text('utf-8')
                loaded = yaml.safe_load(content)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception as e:
                self.log(f"Notice reading config.yaml: {e}")
                
        if "models" not in data or not isinstance(data["models"], list):
            data["models"] = []
            
        models = data["models"]
        # Remove existing GigaChat entries to refresh cleanly
        models = [m for m in models if isinstance(m, dict) and not (m.get("apiBase") == "http://localhost:8090/v2" or str(m.get("name", "")).startswith("GigaChat"))]
        
        # Insert current model at top of models
        giga_entry = {
            "name": f"GigaChat ({selected_model})",
            "provider": "openai",
            "model": selected_model,
            "apiBase": "http://localhost:8090/v2",
            "apiKey": "sk-gigachat",
            "roles": ["chat", "edit", "apply"],
            "useLegacyCompletionsEndpoint": False,
            "defaultCompletionOptions": {
                "contextLength": 32768,
                "maxTokens": 8192
            },
            "capabilities": ["tool_use"]
        }
        models.insert(0, giga_entry)
        data["models"] = models
        
        CONTINUE_CONFIG.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), 'utf-8')
        self.log(f"Patched Continue.dev config: {CONTINUE_CONFIG} (Model: {selected_model})")
        QMessageBox.information(self, "Success", f"Continue.dev config.yaml updated with {selected_model}!")

    def test_connection(self):
        creds = self.creds_input.text().strip()
        if not creds:
            QMessageBox.critical(self, "Error", "Please enter GigaChat Credentials first.")
            return

        self.log("Testing connection to GigaChat API...")
        self.test_thread = TestConnectionThread(creds)
        self.test_thread.log_signal.connect(self.log)
        self.test_thread.success_signal.connect(self.on_test_success)
        self.test_thread.error_signal.connect(self.on_test_error)
        self.test_thread.start()
        
    def on_test_success(self, models):
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if "GigaChat-3-Ultra" in models:
            self.model_combo.setCurrentText("GigaChat-3-Ultra")
        elif "GigaChat-Max" in models:
            self.model_combo.setCurrentText("GigaChat-Max")
        QMessageBox.information(self, "Connection Success", f"Successfully connected!\n\nAvailable models:\n{', '.join(models)}")
        
    def on_test_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def make_backup(self, path: Path):
        if not path.exists():
            return False
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        self.log(f"Created backup: {backup_path}")
        return True

    def restore_backup(self, path: Path):
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup_path.exists():
            shutil.copy2(backup_path, path)
            self.log(f"Restored backup: {path}")
            QMessageBox.information(self, "Success", f"Restored config for {path.name}")
        else:
            QMessageBox.critical(self, "Error", f"No backup found for {path.name}")

    def patch_codex(self):
        selected_model = self.model_combo.currentText()
        if not CODEX_CONFIG.parent.exists():
            CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            
        if CODEX_CONFIG.exists():
            self.make_backup(CODEX_CONFIG)
            content = CODEX_CONFIG.read_text('utf-8')
        else:
            content = ""

        if "model_provider = \"gpt2giga\"" not in content:
            new_config = f"""
model = "{selected_model}"
model_provider = "gpt2giga"
model_reasoning_effort = "none"

[model_providers.gpt2giga]
name = "gpt2giga"
base_url = "http://localhost:8090/v2"
env_key = "GPT2GIGA_API_KEY"
wire_api = "responses"
supports_websockets = false
"""
            with open(CODEX_CONFIG, "a", encoding="utf-8") as f:
                f.write("\n" + new_config)

        # 1. Update SQLite DBs
        from_provider = "openai"
        to_provider = "gpt2giga"
        db_changes = 0
        
        db1 = Path.home() / ".codex" / "state_5.sqlite"
        if db1.exists():
            self.make_backup(db1)
            try:
                conn = sqlite3.connect(db1)
                cursor = conn.cursor()
                cursor.execute(f"UPDATE threads SET model_provider = ? WHERE model_provider = ?", (to_provider, from_provider))
                db_changes += cursor.rowcount
                conn.commit()
                conn.close()
            except Exception as e:
                self.log(f"SQLite Update Error (state_5): {e}")

        db2 = Path.home() / ".codex" / "sqlite" / "codex-dev.db"
        if db2.exists():
            self.make_backup(db2)
            try:
                conn = sqlite3.connect(db2)
                cursor = conn.cursor()
                cursor.execute(f"UPDATE local_thread_catalog SET model_provider = ? WHERE model_provider = ?", (to_provider, from_provider))
                db_changes += cursor.rowcount
                conn.commit()
                conn.close()
            except Exception as e:
                self.log(f"SQLite Update Error (codex-dev): {e}")

        # 2. Update JSONL Chat History
        jsonl_changes = 0
        needle = f'"model_provider":"{from_provider}"'
        replacement = f'"model_provider":"{to_provider}"'
        
        for folder in ["sessions", "archived_sessions"]:
            target_dir = Path.home() / ".codex" / folder
            if not target_dir.exists():
                continue
            for file in target_dir.rglob("*.jsonl"):
                try:
                    text = file.read_text(encoding="utf-8")
                    if needle in text:
                        self.make_backup(file)
                        file.write_text(text.replace(needle, replacement), encoding="utf-8")
                        jsonl_changes += 1
                except Exception:
                    pass

        # 3. Write auth.json
        auth_path = Path.home() / ".codex" / "auth.json"
        self.make_backup(auth_path)
        auth_data = {
            "auth_mode": "apikey",
            "OPENAI_API_KEY": "sk-gigachat"
        }
        with open(auth_path, "w", encoding="utf-8") as f:
            json.dump(auth_data, f, indent=4)

        # 4. Set Windows Environment Variables
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
            self.log(f"Env Var Error: {e}")

        self.log(f"Patched Codex config, auth.json, and Environment vars.")
        self.log(f"Chat migration: {jsonl_changes} JSONL files patched, {db_changes} SQLite rows updated.")
        QMessageBox.information(self, "Success", f"Patched Codex!\n\nMigrated {jsonl_changes} JSONL files and {db_changes} SQLite rows.\nauth.json and Windows Env Vars updated.")

    def patch_json_config(self, path: Path, name: str):
        selected_model = self.model_combo.currentText()
        if not path.exists():
            self.log(f"Config file not found for {name}: {path}")
            QMessageBox.warning(self, "Warning", f"Config file not found for {name}:\n{path}\n\nYou may need to open the app once to generate it.")
            return
        
        self.make_backup(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if "openai" not in data:
                data["openai"] = {}
            data["openai"]["baseURL"] = "http://localhost:8090/v2"
            data["openai"]["apiKey"] = "sk-gigachat"
            data["openai"]["model"] = selected_model
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.log(f"Patched {name} config: {path}")
            QMessageBox.information(self, "Success", f"Patched {name} config with model {selected_model}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to patch {name}: {e}")

    def patch_vscode_config(self):
        selected_model = self.model_combo.currentText()
        if not VSCODE_CONFIG.parent.exists():
            VSCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            
        if not VSCODE_CONFIG.exists():
            with open(VSCODE_CONFIG, "w", encoding="utf-8") as f:
                f.write("{}")

        self.make_backup(VSCODE_CONFIG)
        try:
            with open(VSCODE_CONFIG, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    data = {}
                else:
                    data = json.loads(content)
            
            data["codex.apiKey"] = "sk-gigachat"
            data["codex.apiBaseUrl"] = "http://localhost:8090/v2"
            data["codex.model"] = selected_model
            data["openai.apiKey"] = "sk-gigachat"
            data["openai.baseURL"] = "http://localhost:8090/v2"
            
            with open(VSCODE_CONFIG, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.log(f"Patched VS Code config: {VSCODE_CONFIG}")
            QMessageBox.information(self, "Success", f"Patched VS Code settings.json with model {selected_model}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to patch VS Code: {e}")

    def patch_vscode_extension(self):
        patched = 0
        already = 0
        
        home = Path.home()
        roots = [home / ".vscode" / "extensions", home / ".vscode-server" / "extensions"]
        
        for root in roots:
            if not root.exists():
                continue
                
            for ext_dir in root.glob("openai.chatgpt-*"):
                assets_dir = ext_dir / "webview" / "assets"
                if not assets_dir.exists():
                    continue
                    
                for js_file in assets_dir.glob("*.js"):
                    try:
                        with open(js_file, "r", encoding="utf-8") as f:
                            text = f.read()
                    except Exception:
                        continue
                        
                    is_candidate = ('fast_mode' in text or 'additionalSpeedTiers' in text or 'a===`chatgpt`' in text or 't===`chatgpt`' in text)
                    if not is_candidate:
                        continue
                        
                    if '||e===`apikey`' in text or '===`chatgpt`||a===`apikey`' in text or '===`chatgpt`||t===`apikey`' in text:
                        already += 1
                        continue
                        
                    updated = text.replace('a===`chatgpt`', 'a===`chatgpt`||a===`apikey`').replace('t===`chatgpt`', 't===`chatgpt`||t===`apikey`')
                    
                    import re
                    if updated == text:
                        updated = re.sub(r'function ([A-Za-z_$][\w$]*)\(e\)\{return e===`chatgpt`\}', r'function \1(e){return e===`chatgpt`||e===`apikey`}', text, count=1)
                        
                    if updated == text:
                        continue
                        
                    backup = js_file.with_suffix(".js.bak-gpt2giga")
                    if not backup.exists():
                        shutil.copy2(js_file, backup)
                        
                    with open(js_file, "w", encoding="utf-8") as f:
                        f.write(updated)
                    patched += 1
                    
        if patched > 0:
            QMessageBox.information(self, "Success", f"Patched {patched} VS Code extension files.\nPlease restart VS Code.")
        elif already > 0:
            QMessageBox.information(self, "Info", f"VS Code extension already patched ({already} files).")
        else:
            QMessageBox.warning(self, "Warning", "VS Code extension files not found or not recognized.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProxyManagerApp()
    window.show()
    sys.exit(app.exec())
