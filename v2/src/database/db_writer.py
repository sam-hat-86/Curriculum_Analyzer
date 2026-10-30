"""
単一DB Writer スレッド (仕様書§3, §6: SQLiteロック競合防止・全書き込み集約・高速バッチコミット)
"""
from dataclasses import dataclass
import queue
import threading
import time
from typing import Optional, Callable
from src.database.repository import Repository
from src.models.curriculum import CurriculumDetailData
from src.utils.logger import get_logger


@dataclass(slots=True)
class FetchedHtmlItem:
    """クローラーがHTML取得成功した際の非同期保存キューアイテム"""
    page_key: str
    html: str
    fetch_time: str


@dataclass(slots=True)
class FetchFailedItem:
    """クローラーがHTML取得失敗(スキップ)した際の非同期保存キューアイテム"""
    page_key: str
    error_message: str


class DBWriter(threading.Thread):
    def __init__(
        self,
        repository: Repository,
        save_queue: queue.Queue,
        checkpoint_interval: int = 0,
        checkpoint_callback: Optional[Callable[[int], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        batch_size: int = 25,
        flush_interval_sec: float = 0.2,
    ):
        super().__init__(name="DBWriterThread", daemon=True)
        self.repository = repository
        self.save_queue = save_queue
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback
        self.batch_size = max(1, batch_size)
        self.flush_interval_sec = max(0.05, flush_interval_sec)
        self.is_running = True
        self.saved_count = 0
        self.logger = get_logger()

    def _process_single_item(self, item, conn) -> bool:
        """1件のアイテムをトランザクション内で処理。解析結果の保存なら True を返す"""
        if isinstance(item, CurriculumDetailData):
            self.repository.save_parsed_result(item, conn=conn, commit=False)
            self.saved_count += 1
            if self.checkpoint_interval > 0 and self.saved_count % self.checkpoint_interval == 0:
                if self.checkpoint_callback:
                    try:
                        conn.commit()
                        self.checkpoint_callback(self.saved_count)
                    except Exception as e:
                        self.logger.error(f"中間保存コールバック実行エラー: {e}")
            return True
        elif isinstance(item, FetchedHtmlItem):
            self.repository.update_page_fetched(
                item.page_key, item.html, item.fetch_time, conn=conn, commit=False
            )
            return False
        elif isinstance(item, FetchFailedItem):
            self.repository.update_page_fetch_failed(
                item.page_key, item.error_message, conn=conn, commit=False
            )
            return False
        else:
            self.logger.warning(f"未知のキューアイテムを受信: {type(item)}")
            return False

    def run(self):
        self.logger.info("DBWriterスレッドが開始されました (接続永続化・高速バッチモード)")
        conn = self.repository.db.get_connection()
        last_progress_emit = 0.0
        try:
            while self.is_running:
                try:
                    first_item = self.save_queue.get(timeout=0.3)
                except queue.Empty:
                    continue

                batch = [first_item]
                stop_signal_received = (first_item is None)

                # キューに溜まっている後続アイテムを batch_size まで一括取り出し
                if not stop_signal_received:
                    deadline = time.monotonic() + self.flush_interval_sec
                    while len(batch) < self.batch_size:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        try:
                            nxt = self.save_queue.get_nowait()
                            batch.append(nxt)
                            if nxt is None:
                                stop_signal_received = True
                                break
                        except queue.Empty:
                            break

                parsed_saved_in_batch = False
                try:
                    for item in batch:
                        if item is None:
                            continue
                        try:
                            if self._process_single_item(item, conn):
                                parsed_saved_in_batch = True
                        except Exception as item_err:
                            self.logger.error(f"DB保存処理中にエラーが発生しました: {item_err}", exc_info=True)
                    conn.commit()
                except Exception as commit_err:
                    self.logger.error(f"DBバッチコミットエラー: {commit_err}", exc_info=True)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                finally:
                    for _ in batch:
                        self.save_queue.task_done()

                if parsed_saved_in_batch and self.progress_callback:
                    now = time.monotonic()
                    if stop_signal_received or self.save_queue.empty() or (now - last_progress_emit >= 0.3):
                        last_progress_emit = now
                        try:
                            self.progress_callback(self.saved_count)
                        except Exception as cb_err:
                            self.logger.debug(f"進捗コールバックエラー: {cb_err}")

                if stop_signal_received:
                    break
        finally:
            try:
                conn.commit()
                conn.close()
            except Exception:
                pass
            self.logger.info(f"DBWriterスレッドが終了しました (総保存件数: {self.saved_count})")

    def stop(self):
        self.is_running = False
