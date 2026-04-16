"""Tests for the manual directory picker dialog and last-instance persistence.

Covers:
  - load_last_instance / save_last_instance round-trip
  - load_last_instance returns None for missing, corrupt, or stale entries
  - detect_instance_root uses the last-instance cache as a fallback step
  - pick_mods_directory happy path (dialog accepted, path saved)
  - pick_mods_directory cancel — sys.exit(1) is called
  - pick_mods_directory with empty mods folder — validation warning shown,
    user can proceed or cancel
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from oar_priority_manager.app.config import (
    DetectionError,
    detect_instance_root,
    load_last_instance,
    save_last_instance,
)

#: Real enum values — kept on mock classes so comparisons in the SUT work.
_OK = QMessageBox.StandardButton.Ok
_CANCEL = QMessageBox.StandardButton.Cancel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_cache(cache_path: Path, mods_path: str) -> None:
    """Write a minimal last-instance.json at *cache_path*."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"mods_path": mods_path, "timestamp": "2026-04-15T00:00:00+00:00"}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# load_last_instance / save_last_instance
# ---------------------------------------------------------------------------


class TestLastInstancePersistence:
    """Round-trip and failure-mode tests for the cache helpers."""

    def test_save_creates_file(self, tmp_path: Path, monkeypatch) -> None:
        """save_last_instance writes a JSON file in the appdata directory."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()

        save_last_instance(mods)

        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        assert cache.is_file()

    def test_save_and_load_roundtrip(self, tmp_path: Path, monkeypatch) -> None:
        """Saved path is returned verbatim by load_last_instance."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()

        save_last_instance(mods)
        result = load_last_instance()

        assert result == mods

    def test_save_stores_mods_path_string(self, tmp_path: Path, monkeypatch) -> None:
        """The JSON file contains a ``mods_path`` key."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()

        save_last_instance(mods)

        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        data = json.loads(cache.read_text(encoding="utf-8"))
        assert "mods_path" in data
        assert data["mods_path"] == str(mods)

    def test_save_stores_timestamp(self, tmp_path: Path, monkeypatch) -> None:
        """The JSON file contains a ``timestamp`` key."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()

        save_last_instance(mods)

        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        data = json.loads(cache.read_text(encoding="utf-8"))
        assert "timestamp" in data

    def test_load_missing_file_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """load_last_instance returns None when the cache file is absent."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        result = load_last_instance()
        assert result is None

    def test_load_corrupt_json_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """load_last_instance returns None when the file contains invalid JSON."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("not valid json!!!", encoding="utf-8")

        result = load_last_instance()
        assert result is None

    def test_load_missing_key_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """load_last_instance returns None when ``mods_path`` key is absent."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"timestamp": "2026-04-15"}), encoding="utf-8")

        result = load_last_instance()
        assert result is None

    def test_load_stale_path_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        """load_last_instance returns None when the cached directory no longer exists."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        ghost_path = tmp_path / "gone" / "mods"  # never created
        cache = tmp_path / "oar-priority-manager" / "last-instance.json"
        _write_cache(cache, str(ghost_path))

        result = load_last_instance()
        assert result is None

    def test_overwrite_updates_cached_path(self, tmp_path: Path, monkeypatch) -> None:
        """Calling save_last_instance twice keeps the most recent path."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        old_mods = tmp_path / "old_mods"
        new_mods = tmp_path / "new_mods"
        old_mods.mkdir()
        new_mods.mkdir()

        save_last_instance(old_mods)
        save_last_instance(new_mods)
        result = load_last_instance()

        assert result == new_mods


# ---------------------------------------------------------------------------
# detect_instance_root — last-instance fallback step
# ---------------------------------------------------------------------------


class TestDetectInstanceRootFallback:
    """The last-instance cache is checked before DetectionError is raised."""

    def test_cache_used_when_auto_detection_fails(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When no MO2 instance is found, the cached mods path is used."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()
        # Simulate a previous successful picker session.
        save_last_instance(mods)

        # cwd has no ModOrganizer.ini — auto-detection will fail.
        empty_cwd = tmp_path / "some" / "other" / "dir"
        empty_cwd.mkdir(parents=True)

        result = detect_instance_root(cwd=empty_cwd)
        # The instance root is the parent of the mods/ directory.
        assert result == tmp_path

    def test_raises_when_cache_also_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """DetectionError is raised when both auto-detection and cache fail."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        # No cache file, no ModOrganizer.ini.
        result_dir = tmp_path / "empty"
        result_dir.mkdir()

        with pytest.raises(DetectionError):
            detect_instance_root(cwd=result_dir)

    def test_cli_arg_takes_priority_over_cache(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Explicit --mods-path overrides any cached path."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        cached_mods = tmp_path / "cached_mods"
        cached_mods.mkdir()
        save_last_instance(cached_mods)

        real_mods = tmp_path / "real_mods"
        real_mods.mkdir()

        result = detect_instance_root(mods_path=str(real_mods))
        assert result == tmp_path
        assert result == real_mods.parent

    def test_mo_ini_takes_priority_over_cache(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A found ModOrganizer.ini is used before consulting the cache."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        # Instance in a sub-path.
        instance = tmp_path / "instance"
        instance.mkdir()
        (instance / "ModOrganizer.ini").touch()
        (instance / "mods").mkdir()

        # Cache points somewhere else.
        other_mods = tmp_path / "other_mods"
        other_mods.mkdir()
        save_last_instance(other_mods)

        result = detect_instance_root(cwd=instance)
        assert result == instance


# ---------------------------------------------------------------------------
# pick_mods_directory — dialog behaviour (mocked Qt)
# ---------------------------------------------------------------------------


class TestPickModsDirectory:
    """Verifies dialog flow via monkeypatched Qt calls."""

    def _make_app(self):
        """Return a mock QApplication instance."""
        app = MagicMock()
        return app

    def test_happy_path_returns_chosen_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Chosen directory is returned and persisted to the cache."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()
        # Populate with a subdirectory so validation passes.
        (mods / "SomeMod").mkdir()

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox"
            ) as mock_mb_cls,
            patch(
                "oar_priority_manager.ui.instance_picker.QFileDialog"
                ".getExistingDirectory",
                return_value=str(mods),
            ),
        ):
            # Preserve real enum values so comparisons in the SUT work.
            mock_mb_cls.StandardButton = QMessageBox.StandardButton
            mock_mb_cls.Icon = QMessageBox.Icon
            mock_mb_instance = MagicMock()
            mock_mb_instance.exec.return_value = _OK
            mock_mb_cls.return_value = mock_mb_instance

            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            result = pick_mods_directory(self._make_app())

        assert result == mods

    def test_happy_path_saves_to_cache(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """After a successful pick, the path is written to last-instance.json."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()
        (mods / "SomeMod").mkdir()

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox"
            ) as mock_mb_cls,
            patch(
                "oar_priority_manager.ui.instance_picker.QFileDialog"
                ".getExistingDirectory",
                return_value=str(mods),
            ),
        ):
            mock_mb_cls.StandardButton = QMessageBox.StandardButton
            mock_mb_cls.Icon = QMessageBox.Icon
            mock_mb_instance = MagicMock()
            mock_mb_instance.exec.return_value = _OK
            mock_mb_cls.return_value = mock_mb_instance

            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            pick_mods_directory(self._make_app())

        cached = load_last_instance()
        assert cached == mods

    def test_info_dialog_cancel_exits(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Cancelling the intro QMessageBox calls sys.exit(1)."""
        monkeypatch.setenv("APPDATA", str(tmp_path))

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox"
            ) as mock_mb_cls,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_mb_cls.StandardButton = QMessageBox.StandardButton
            mock_mb_cls.Icon = QMessageBox.Icon
            mock_mb_instance = MagicMock()
            mock_mb_instance.exec.return_value = _CANCEL
            mock_mb_cls.return_value = mock_mb_instance

            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            pick_mods_directory(self._make_app())

        assert exc_info.value.code == 1

    def test_file_dialog_cancel_exits(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Returning an empty string from getExistingDirectory calls sys.exit(1)."""
        monkeypatch.setenv("APPDATA", str(tmp_path))

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox"
            ) as mock_mb_cls,
            patch(
                "oar_priority_manager.ui.instance_picker.QFileDialog"
                ".getExistingDirectory",
                return_value="",
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_mb_cls.StandardButton = QMessageBox.StandardButton
            mock_mb_cls.Icon = QMessageBox.Icon
            mock_mb_instance = MagicMock()
            mock_mb_instance.exec.return_value = _OK
            mock_mb_cls.return_value = mock_mb_instance

            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            pick_mods_directory(self._make_app())

        assert exc_info.value.code == 1

    def test_empty_mods_folder_shows_warning_then_proceeds(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """An empty mods folder triggers a warning; user can still proceed."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()
        # No subdirectories — validation will flag this.

        call_count = [0]

        class _FakeMBClass:
            """Stand-in for QMessageBox that preserves real enum attrs."""

            StandardButton = QMessageBox.StandardButton
            Icon = QMessageBox.Icon
            Option = QMessageBox.Option

            def __init__(self, *args, **kwargs):
                call_count[0] += 1

            def setWindowTitle(self, *a):
                pass

            def setIcon(self, *a):
                pass

            def setText(self, *a):
                pass

            def setStandardButtons(self, *a):
                pass

            def setDefaultButton(self, *a):
                pass

            def exec(self):
                # Both info and warning dialogs return Ok.
                return _OK

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox",
                _FakeMBClass,
            ),
            patch(
                "oar_priority_manager.ui.instance_picker.QFileDialog"
                ".getExistingDirectory",
                return_value=str(mods),
            ),
        ):
            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            result = pick_mods_directory(self._make_app())

        # Both the info dialog and the warning dialog were shown.
        assert call_count[0] == 2
        assert result == mods

    def test_empty_mods_folder_warning_cancel_exits(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Cancelling the empty-folder warning calls sys.exit(1)."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        mods = tmp_path / "mods"
        mods.mkdir()

        call_count = [0]

        class _FakeMBClassCancel:
            """Stand-in: info → Ok, warning → Cancel."""

            StandardButton = QMessageBox.StandardButton
            Icon = QMessageBox.Icon
            Option = QMessageBox.Option

            def __init__(self, *args, **kwargs):
                call_count[0] += 1

            def setWindowTitle(self, *a):
                pass

            def setIcon(self, *a):
                pass

            def setText(self, *a):
                pass

            def setStandardButtons(self, *a):
                pass

            def setDefaultButton(self, *a):
                pass

            def exec(self):
                if call_count[0] == 1:
                    return _OK
                return _CANCEL

        with (
            patch(
                "oar_priority_manager.ui.instance_picker.QMessageBox",
                _FakeMBClassCancel,
            ),
            patch(
                "oar_priority_manager.ui.instance_picker.QFileDialog"
                ".getExistingDirectory",
                return_value=str(mods),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            pick_mods_directory(self._make_app())

        assert exc_info.value.code == 1

    def test_no_qapplication_raises_runtime_error(
        self, monkeypatch
    ) -> None:
        """RuntimeError is raised when no QApplication exists."""
        with patch(
            "oar_priority_manager.ui.instance_picker.QApplication"
            ".instance",
            return_value=None,
        ):
            from oar_priority_manager.ui.instance_picker import pick_mods_directory

            with pytest.raises(RuntimeError, match="QApplication"):
                pick_mods_directory(None)
