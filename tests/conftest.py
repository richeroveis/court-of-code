"""Pytest configuration and Windows compatibility shim for gltest direct mode.

On Windows, the GenLayer direct-mode test runner creates short-lived temp files
and tries to unlink them while the sandbox process may still hold an open handle,
which raises PermissionError / OSError and can abort a whole test run even though
the assertions already passed. This shim defers those failed unlinks: we swallow
the error, remember the path, and best-effort clean it up at session teardown.
"""

import os
import pathlib
import tempfile
import time

import pytest

_DEFERRED_UNLINKS: set[str] = set()


def _is_transient_windows_lock(exc: BaseException) -> bool:
    """Return True when this looks like a Windows sharing violation on unlink."""
    if os.name != "nt":
        return False
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        # WinError 32 = The process cannot access the file because it is being
        # used by another process.
        return getattr(exc, "winerror", None) == 32
    return False


def _patched_unlink(self, *args, **kwargs):
    missing_ok = kwargs.pop("missing_ok", False)
    try:
        return pathlib.Path.unlink(self, *args, **kwargs)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    except Exception as exc:  # noqa: BLE001 - only swallow the Windows lock
        if _is_transient_windows_lock(exc):
            _DEFERRED_UNLINKS.add(str(self))
            return None
        raise


def _patched_os_remove(path, *args, **kwargs):
    try:
        return os.__remove__(path, *args, **kwargs)
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001 - only swallow the Windows lock
        if _is_transient_windows_lock(exc):
            _DEFERRED_UNLINKS.add(str(path))
            return None
        raise


def _patched_os_unlink(path, *args, **kwargs):
    try:
        return os.__unlink__(path, *args, **kwargs)
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001 - only swallow the Windows lock
        if _is_transient_windows_lock(exc):
            _DEFERRED_UNLINKS.add(str(path))
            return None
        raise


def pytest_configure(config):
    """Install the deferred-unlink shim before any test collection happens."""
    # Keep a reference to the original so the patch is idempotent.
    if not hasattr(os, "__remove__"):
        os.__remove__ = os.remove
    if not hasattr(os, "__unlink__"):
        os.__unlink__ = os.unlink
    if not hasattr(pathlib.Path, "_gltest_original_unlink"):
        pathlib.Path._gltest_original_unlink = pathlib.Path.unlink
        pathlib.Path.unlink = _patched_unlink
    if not hasattr(os, "_gltest_original_remove"):
        os._gltest_original_remove = os.__remove__
        os.remove = _patched_os_remove
    if not hasattr(os, "_gltest_original_unlink"):
        os._gltest_original_unlink = os.__unlink__
        os.unlink = _patched_os_unlink


@pytest.fixture(autouse=True)
def _pin_temp_dir():
    """Give every direct-mode test a stable, disposable temp directory."""
    prev = tempfile.gettempdir()
    with tempfile.TemporaryDirectory(prefix="courtcode_") as tmp:
        os.environ["TMPDIR"] = tmp
        os.environ["TEMP"] = tmp
        os.environ["TMP"] = tmp
        yield tmp
    # tempfile.gettempdir memoizes; nothing else to restore beyond env.
    assert prev is not None


def pytest_sessionfinish(session, exitstatus):
    """Best-effort cleanup of any temp paths whose unlink was deferred."""
    deadline = time.time() + 5.0
    for path in list(_DEFERRED_UNLINKS):
        while time.time() < deadline:
            try:
                if os.path.isdir(path):
                    os.rmdir(path)
                elif os.path.exists(path):
                    os.__remove__(path)
                _DEFERRED_UNLINKS.discard(path)
                break
            except OSError:
                time.sleep(0.1)
