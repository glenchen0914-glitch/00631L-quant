from pathlib import Path

workflow = Path('.github/workflows/daily.yml').read_text(encoding='utf-8')
assert 'Push LINE close report' in workflow
assert 'python -m src.notify' in workflow
assert "LINE_PUSH_REQUIRED: 'true'" in workflow
assert 'LINE_CHANNEL_ACCESS_TOKEN' in workflow
assert 'LINE_USER_ID' in workflow
print('PASS: 14:35 workflow includes required LINE push')
