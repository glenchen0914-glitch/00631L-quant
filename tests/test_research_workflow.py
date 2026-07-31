from pathlib import Path


def test_research_workflow_exists_and_is_manual_weekly():
    text = Path('.github/workflows/research.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch' in text
    assert "cron: '0 0 * * 6'" in text
    assert 'python run_falcon_research.py' in text
    assert 'reports/research/00631L_research.json' in text
    assert 'reports/research/00981A_research.json' in text
