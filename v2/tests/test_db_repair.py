"""
既存DB自動修復 (repair_database_if_needed) の単体テスト (D-4)
"""
from src.database.db_manager import DatabaseManager
from src.database.repository import Repository
from src.database.repair import repair_database_if_needed
from src.models.curriculum import CurriculumOverview
from src.models.state import ProcessState


SAMPLE_DETAIL_HTML = """
<html><body>
<table class="sc2-student-info">
  <tr><th>生徒名</th><td>修復 対象生徒</td><th>学年</th><td>高2</td></tr>
</table>
<table class="def-form-table">
  <tr><th>授業指示</th><td>作成者：山田\n教材：チャート(所持)\n進め方：毎回1単元ずつ進める\n生徒情報：計算が速い\n小テスト：毎回実施80点合格\n宿題：例題復習</td></tr>
</table>
<table class="sc2-sim-target">
  <tbody>
    <tr><td>T1</td><td>1学期中間</td><td>2026/04/01～2026/05/31</td><td>80</td><td>75</td><td>100%</td></tr>
    <tr><td><div class="dl-data"></div></td></tr>
    <tr><td><div class="dl-data"></div></td></tr>
  </tbody>
</table>
<table class="table is-bordered is-striped is-narrow">
  <thead><tr><th>No</th><th>単元</th><th>中単元</th><th>教材</th><th>問題コード</th><th>得点</th><th>配点</th><th>得点率</th><th>実施日</th><th>T1</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>二次関数</td><td>最大最小</td><td>チャート</td><td>M01</td><td>9</td><td>10</td><td>90</td><td>2026/04/20</td><td><input type="checkbox" checked="checked"/></td></tr>
  </tbody>
</table>
</body></html>
"""


def test_repair_database_promotes_fetched_and_removes_orphans(tmp_path):
    """
    旧バージョンの不整合状態:
    - pages には url='1001_S200_数学_2_0', status='FETCHED', html=SAMPLE_DETAIL_HTML が保存されている
    - 子テーブル (units, instruction_evaluations 等) には誤ったキー '1001_S200_数学_0' (孤児レコード) が入っている
    この状態から repair_database_if_needed を実行すると:
    1. '1001_S200_数学_2_0' が再解析され SAVED に昇格し、正しいキーで子レコードが作られる
    2. 誤ったキー '1001_S200_数学_0' の孤児レコードが削除される
    3. 2回目の呼び出しは skipped=True となり高速スキップされる
    """
    db_file = str(tmp_path / "legacy_broken.db")
    db_manager = DatabaseManager(db_file)
    repo = Repository(db_manager)

    ov_page2 = CurriculumOverview(
        classroom_name="難波校", classroom_code="1001", school_year="2026",
        student_id="S200", student_name="修復 対象生徒", grade="高2",
        division="通常", subject="数学", row_index=0, page_index=2
    )
    repo.save_pages_init([ov_page2])
    repo.update_page_fetched(ov_page2.page_key, SAMPLE_DETAIL_HTML, "2026-10-28 12:00:00")

    # 旧バグで発生した孤児レコードを直接挿入 (page_indexサフィックス欠落キー)
    broken_key = "1001_S200_数学_0"
    with db_manager.connect() as conn:
        conn.execute(
            "INSERT INTO instruction_evaluations (page_url, student_id, severity) VALUES (?, ?, ?)",
            (broken_key, "S200", "PASS"),
        )
        conn.execute(
            "INSERT INTO targets (page_url, student_id, target_no, target_name) VALUES (?, ?, ?, ?)",
            (broken_key, "S200", "T1", "孤児ターゲット"),
        )

    counts_before = repo.get_counts()
    assert counts_before["fetched"] == 1
    assert counts_before["saved"] == 0

    # 1回目の修復実行
    res1 = repair_database_if_needed(repo)
    assert res1["skipped"] is False
    assert res1["repaired_pages"] == 1
    assert res1["removed_orphans"] == 2

    counts_after = repo.get_counts()
    assert counts_after["saved"] == 1
    assert counts_after["fetched"] == 0

    # JOINクエリで2ページ目の生徒の備考欄・単元が取得できること
    evals = repo.get_all_instruction_evaluations()
    assert len(evals) == 1
    assert evals[0]["page_url"] == "1001_S200_数学_2_0"
    assert evals[0]["student_name"] == "修復 対象生徒"

    # 2回目の修復実行は user_version により即スキップされること
    res2 = repair_database_if_needed(repo)
    assert res2["skipped"] is True
    assert res2["repaired_pages"] == 0
    assert res2["removed_orphans"] == 0

