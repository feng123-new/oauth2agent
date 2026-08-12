from pathlib import Path

from oauth2agent.mock import run_simulation


def test_simulation(tmp_path: Path):
    report = run_simulation(str(tmp_path))
    assert report.runtime_id == "agent-demo-runtime"
    assert report.task_id == "task-demo-run"
    assert report.response_text == "OK"
    assert report.isolation_status == 403
    assert Path(report.output_file).exists()
