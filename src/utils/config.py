"""
設定ファイル管理 (config.ini / selectors.json)
"""
import configparser
import json
import os
from typing import Dict, Any

DEFAULT_CONFIG_PATH = os.path.join("config", "config.ini")
DEFAULT_SELECTORS_PATH = os.path.join("config", "selectors.json")

class AppConfig:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, selectors_path: str = DEFAULT_SELECTORS_PATH):
        self.config_path = config_path
        self.selectors_path = selectors_path
        
        # デフォルト値
        self.app_name = "カリキュラムチェックシステム"
        self.version = "2.0.0"
        self.max_concurrency = 1
        self.request_interval_sec = 1.0
        self.max_retries = 3
        self.retry_interval_sec = 2.0
        self.timeout_sec = 30
        self.headless = True
        self.worker_threads = 3
        self.db_path = "user_data/curriculum_v2.db"
        self.output_dir = "output/v2"
        self.checkpoint_interval = 100
        self.log_level = "INFO"
        self.log_dir = "logs"
        self.selectors: Dict[str, Any] = {}
        
        self.load()

    def load(self):
        """config.ini と selectors.json を読み込む"""
        if os.path.exists(self.config_path):
            parser = configparser.ConfigParser()
            parser.read(self.config_path, encoding="utf-8")
            
            if "general" in parser:
                self.app_name = parser.get("general", "app_name", fallback=self.app_name)
                self.version = parser.get("general", "version", fallback=self.version)
                
            if "crawler" in parser:
                self.max_concurrency = parser.getint("crawler", "max_concurrency", fallback=1)
                self.request_interval_sec = parser.getfloat("crawler", "request_interval_sec", fallback=1.0)
                self.max_retries = parser.getint("crawler", "max_retries", fallback=3)
                self.retry_interval_sec = parser.getfloat("crawler", "retry_interval_sec", fallback=2.0)
                self.timeout_sec = parser.getint("crawler", "timeout_sec", fallback=30)
                self.headless = parser.getboolean("crawler", "headless", fallback=True)
                
            if "analyzer" in parser:
                self.worker_threads = parser.getint("analyzer", "worker_threads", fallback=3)
                
            if "database" in parser:
                self.db_path = parser.get("database", "db_path", fallback=self.db_path)
                
            if "export" in parser:
                self.output_dir = parser.get("export", "output_dir", fallback=self.output_dir)
                self.checkpoint_interval = parser.getint("export", "checkpoint_interval", fallback=100)
                
            if "logging" in parser:
                self.log_level = parser.get("logging", "log_level", fallback="INFO")
                self.log_dir = parser.get("logging", "log_dir", fallback="logs")
                
        if os.path.exists(self.selectors_path):
            try:
                with open(self.selectors_path, "r", encoding="utf-8") as f:
                    self.selectors = json.load(f)
            except Exception:
                self.selectors = {}

    def save(self):
        """現在の設定を config.ini に保存"""
        parser = configparser.ConfigParser()
        parser["general"] = {
            "app_name": self.app_name,
            "version": self.version,
        }
        parser["crawler"] = {
            "max_concurrency": str(self.max_concurrency),
            "request_interval_sec": str(self.request_interval_sec),
            "max_retries": str(self.max_retries),
            "retry_interval_sec": str(self.retry_interval_sec),
            "timeout_sec": str(self.timeout_sec),
            "headless": str(self.headless),
        }
        parser["analyzer"] = {
            "worker_threads": str(self.worker_threads),
        }
        parser["database"] = {
            "db_path": self.db_path,
        }
        parser["export"] = {
            "output_dir": self.output_dir,
            "checkpoint_interval": str(self.checkpoint_interval),
        }
        parser["logging"] = {
            "log_level": self.log_level,
            "log_dir": self.log_dir,
        }
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            parser.write(f)
