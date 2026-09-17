"""
セキュアログ設定 (仕様書§34, §38)
"""
import logging
import os
import re
from datetime import datetime
from typing import Optional, Callable

_LOG_CALLBACKS = []

class SafeLogFormatter(logging.Formatter):
    """パスワードや認証情報、過剰な個人情報をマスキングするフォーマッタ"""
    _MASK_PATTERNS = [
        (re.compile(r"(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1=******"),
        (re.compile(r"(api[_-]?key|token|auth)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1=******"),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern, repl in self._MASK_PATTERNS:
            msg = pattern.sub(repl, msg)
        return msg

class CallbackHandler(logging.Handler):
    """GUIへのリアルタイム通知用ハンドラ"""
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            for cb in _LOG_CALLBACKS:
                try:
                    cb(msg, record.levelname)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)

def add_log_callback(cb: Callable[[str, str], None]):
    """GUIログビューアなどのリスナーを登録"""
    if cb not in _LOG_CALLBACKS:
        _LOG_CALLBACKS.append(cb)

def remove_log_callback(cb: Callable[[str, str], None]):
    if cb in _LOG_CALLBACKS:
        _LOG_CALLBACKS.remove(cb)

def setup_logger(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """ロガーをセットアップ"""
    logger = logging.getLogger("CurriculumAnalyzer")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    if not logger.handlers:
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"analyzer_{today}.log")
        
        formatter = SafeLogFormatter(
            "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # ファイルハンドラ
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        # コンソールハンドラ
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # コールバックハンドラ (GUI用)
        cb_handler = CallbackHandler()
        cb_handler.setFormatter(formatter)
        logger.addHandler(cb_handler)
        
    return logger

def get_logger() -> logging.Logger:
    return logging.getLogger("CurriculumAnalyzer")
