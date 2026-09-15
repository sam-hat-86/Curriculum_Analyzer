import sys
from pathlib import Path

# テスト実行時のバイトコード (__pycache__) 自動生成を抑止
sys.dont_write_bytecode = True

base_dir = Path(__file__).resolve().parent.parent
src_dir = base_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))
tools_dir = base_dir / "tools"
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))



def pytest_unconfigure(config):
    """テストセッション完了時にpytestやPythonによって生成された一時キャッシュを自動完全削除"""
    import shutil
    # tests/__pycache__ のクリーンアップ
    cache_dir = Path(__file__).parent / "__pycache__"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    # tools/__pycache__ のクリーンアップ
    tools_cache = Path(__file__).parent.parent / "tools" / "__pycache__"
    if tools_cache.exists():
        shutil.rmtree(tools_cache, ignore_errors=True)
    # ルートの .pytest_cache のクリーンアップ (環境変数未設定の環境でのフォールバック)
    pytest_cache = Path(config.rootpath) / ".pytest_cache"
    if pytest_cache.exists():
        shutil.rmtree(pytest_cache, ignore_errors=True)



