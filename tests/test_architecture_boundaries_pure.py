from pathlib import Path

def _project_root() -> Path:
    # tests/ is in the project root in your repo
    return Path(__file__).resolve().parents[1]

def test_category_manager_has_no_utils_imports():
    src = (_project_root() / "category_manager.py").read_text(encoding="utf-8")
    assert "from utils" not in src

def test_dialog_never_calls_candidate_label_directly():
    src = (_project_root() / "category_manager.py").read_text(encoding="utf-8")
    assert "candidate_label(" not in src