"""
単一DB Writer スレッド (仕様書§3, §6: SQLiteロック競合防止)
"""
import queue
import threading
import time
from typing import Optional, Callable
from src.database.repository import Repository
from src.models.curriculum import CurriculumDetailData
from src.utils.logger import get_logger

class DBWriter(threading.Thread):
    def __init__(
        self,
        repository: Repository,
        save_queue: queue.Queue,
        checkpoint_interval: int = 100,
        checkpoint_callback: Optional[Callable[[int], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ):
        super().__init__(name="DBWriterThread", daemon=True)
        self.repository = repository
        self.save_queue = save_queue
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback
        self.is_running = True
        self.saved_count = 0
        self.logger = get_logger()

    def run(self):
        self.logger.info("DBWriterスレッドが開始されました")
        while self.is_running:
            try:
                # タイムアウト付きでキューを取得
                item = self.save_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                # 停止シグナル
                self.save_queue.task_done()
                break

            try:
                if isinstance(item, CurriculumDetailData):
                    self.repository.save_parsed_result(item)
                    self.saved_count += 1
                    
                    if self.progress_callback:
                        self.progress_callback(self.saved_count)

                    # 中間保存チェック (仕様書§27)
                    if self.checkpoint_interval > 0 and self.saved_count % self.checkpoint_interval == 0:
                        if self.checkpoint_callback:
                            try:
                                self.checkpoint_callback(self.saved_count)
                            except Exception as e:
                                self.logger.error(f"中間保存コールバック実行エラー: {e}")
                else:
                    self.logger.warning(f"未知のキューアイテムを受信: {type(item)}")
            except Exception as e:
                self.logger.error(f"DB保存処理中にエラーが発生しました: {e}", exc_info=True)
            finally:
                self.save_queue.task_done()

        self.logger.info(f"DBWriterスレッドが終了しました (総保存件数: {self.saved_count})")

    def stop(self):
        self.is_running = False
