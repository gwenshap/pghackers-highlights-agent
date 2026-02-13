# tests/test_main.py
import os
from datetime import date
from src.main import load_previous_digests, save_digest


def test_load_previous_digests_reads_recent_files(tmp_path):
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    (digests_dir / "2026-02-10.md").write_text("digest 10")
    (digests_dir / "2026-02-11.md").write_text("digest 11")
    (digests_dir / "2026-02-12.md").write_text("digest 12")
    (digests_dir / "2026-02-08.md").write_text("digest 08")

    result = load_previous_digests(str(digests_dir), date(2026, 2, 13), days=3)
    assert len(result) == 3
    assert "digest 10" in result[0]
    assert "digest 12" in result[2]


def test_save_digest_creates_file(tmp_path):
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    save_digest(str(digests_dir), date(2026, 2, 13), "my digest content")
    path = digests_dir / "2026-02-13.md"
    assert path.exists()
    assert path.read_text() == "my digest content"
