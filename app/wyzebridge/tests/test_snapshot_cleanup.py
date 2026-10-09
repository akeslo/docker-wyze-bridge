import os
import time
from unittest import mock

import pytest

from wyzebridge import snapshot_manager
from wyzebridge.snapshot_manager import SnapshotManager


def _age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


@pytest.fixture
def img_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_manager, "IMG_PATH", str(tmp_path))
    monkeypatch.setattr(snapshot_manager, "SNAPSHOT_FORMAT", "jpg")
    return tmp_path


def _make(img_dir, name, age_seconds):
    sub = img_dir / "cam1"
    sub.mkdir(exist_ok=True)
    f = sub / name
    f.write_text("x")
    _age(f, age_seconds)
    return f


@pytest.mark.parametrize(
    "keep, age_seconds, expect_deleted",
    [
        ("2d", 3 * 86400, True),
        ("2d", 1 * 86400, False),
        ("24h", 25 * 3600, True),
        ("24h", 23 * 3600, False),
        ("3", 4 * 86400, True),
        ("3", 2 * 86400, False),
        (" 1H ", 2 * 3600, True),
    ],
)
def test_keep_suffix_parsing(img_dir, monkeypatch, keep, age_seconds, expect_deleted):
    monkeypatch.setattr(snapshot_manager, "SNAPSHOT_KEEP", keep)
    f = _make(img_dir, "a.jpg", age_seconds)
    SnapshotManager({}).cleanup()
    assert (not f.exists()) is expect_deleted


def test_unrecognized_value_warns_and_defaults_to_seven_days(img_dir, monkeypatch):
    monkeypatch.setattr(snapshot_manager, "SNAPSHOT_KEEP", "soon")
    old = _make(img_dir, "old.jpg", 8 * 86400)
    new = _make(img_dir, "new.jpg", 6 * 86400)
    with mock.patch.object(snapshot_manager.logger, "warning") as warn:
        SnapshotManager({}).cleanup()
    warn.assert_called_once()
    assert not old.exists()
    assert new.exists()


def test_latest_thumbnails_in_root_are_kept(img_dir, monkeypatch):
    monkeypatch.setattr(snapshot_manager, "SNAPSHOT_KEEP", "1d")
    root_file = img_dir / "cam1.jpg"
    root_file.write_text("x")
    _age(root_file, 10 * 86400)
    SnapshotManager({}).cleanup()
    assert root_file.exists()
