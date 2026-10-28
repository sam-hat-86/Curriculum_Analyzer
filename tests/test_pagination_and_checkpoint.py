"""
中間出力廃止および自動ページネーション機能のテスト
"""
import os
import json
import pytest
from unittest.mock import MagicMock

from src.models.curriculum import CurriculumOverview
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.database.db_writer import DBWriter
from src.exporter.safe_writer import SafeExcelWriter
from src.parser.list_parser import ListParser
from src.browser.pagination import (
    CHECK_NEXT_PAGE_JS,
    CLICK_NEXT_PAGE_JS,
    get_check_page_changed_js,
)
from src.utils.config import AppConfig


def test_checkpoint_export_abolished(tmp_path):
    """中間出力が廃止され、export_checkpointがファイルを出力しないことを検証"""
    out_dir = str(tmp_path / "out")
    writer = SafeExcelWriter(exporter=MagicMock(), output_dir=out_dir)

    result = writer.export_checkpoint(100)
    assert result == ""
    # 出力フォルダにファイルが生成されていないこと
    assert len(os.listdir(out_dir)) == 0


def test_db_writer_no_checkpoint_callback(tmp_path):
    """DBWriterが中間保存コールバックを実行しないこと（デフォルトcheckpoint_interval=0）"""
    db_file = str(tmp_path / "test.db")
    repo = Repository(DatabaseManager(db_file))

    import queue
    q = queue.Queue()
    mock_cb = MagicMock()

    writer = DBWriter(
        repository=repo,
        save_queue=q,
        checkpoint_interval=0,
        checkpoint_callback=mock_cb,
    )
    assert writer.checkpoint_interval == 0
    assert not mock_cb.called


def test_multi_page_overview_and_repository(tmp_path):
    """複数ページにわたるカリキュラム一覧がページごとに識別されDBに保存されること"""
    db_file = str(tmp_path / "test_pages.db")
    repo = Repository(DatabaseManager(db_file))

    # ページ1の生徒
    ov_p1 = CurriculumOverview(
        classroom_name="本校",
        classroom_code="100",
        school_year="2026",
        student_id="STU_001",
        student_name="生徒A",
        grade="高1",
        division="通常",
        subject="英語",
        row_index=0,
        page_index=1,
    )
    # ページ2の生徒 (同classroom, 同student, 同subjectでもpage_indexが異なる)
    ov_p2 = CurriculumOverview(
        classroom_name="本校",
        classroom_code="100",
        school_year="2026",
        student_id="STU_001",
        student_name="生徒A",
        grade="高1",
        division="通常",
        subject="英語",
        row_index=0,
        page_index=2,
    )

    repo.save_pages_init([ov_p1])
    repo.save_pages_init([ov_p2])

    with repo.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url, curriculum_key FROM pages ORDER BY row_index ASC, url ASC")
        rows = cursor.fetchall()
        assert len(rows) == 2
        # 1ページ目は "100_STU_001_英語_0"
        assert rows[0]["url"] == "100_STU_001_英語_0"
        # 2ページ目は "100_STU_001_英語_2_0"
        assert rows[1]["url"] == "100_STU_001_英語_2_0"


def test_list_parser_page_index():
    """ListParserがpage_indexを正しくCurriculumOverviewへ設定すること"""
    mock_html = """
    <table>
        <thead>
            <tr>
                <th>学校/コース</th>
                <th>学年</th>
                <th>受講区分</th>
                <th>科目</th>
                <th>生徒</th>
                <th>シミュレーションシート</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>高校</td>
                <td>高1</td>
                <td>通常</td>
                <td>数学</td>
                <td>STU001 山田太郎</td>
                <td><button>シミュレーションシート</button></td>
            </tr>
        </tbody>
    </table>
    """
    parser = ListParser()
    overviews = parser.parse(mock_html, classroom_name="梅田", classroom_code="001", school_year="2026", page_index=3)
    assert len(overviews) == 1
    assert overviews[0].student_id == "STU001"
    assert overviews[0].page_index == 3
    assert overviews[0].row_index == 0


def test_pagination_js_constants():
    """ページネーションJavaScriptスクリプトが正しく生成されていること"""
    assert "btn-next" in CHECK_NEXT_PAGE_JS
    assert "次へ" in CHECK_NEXT_PAGE_JS
    assert "hasNext" in CHECK_NEXT_PAGE_JS

    assert "btn-next" in CLICK_NEXT_PAGE_JS
    assert "prevSignature" in CLICK_NEXT_PAGE_JS

    changed_js = get_check_page_changed_js("sample_sig")
    assert "sample_sig" in changed_js
    assert "isLoading" in changed_js
    assert "changed" in changed_js
