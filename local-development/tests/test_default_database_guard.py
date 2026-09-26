"""The default-database guard in conftest.py (#371): driven directly, in tmp_path, never in the checkout."""
import pytest

import conftest as guards


def _start_guard():
    guard = guards.no_default_database_in_the_working_directory.__wrapped__()
    next(guard)
    return guard


def _finish_guard(guard) -> None:
    with pytest.raises(StopIteration):
        next(guard)


def test_an_unchanged_existing_database_passes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "gsd.db").write_bytes(b"a developer's database")
    _finish_guard(_start_guard())


def test_changing_directory_does_not_blame_another_directorys_database(tmp_path, monkeypatch) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "gsd.db").write_bytes(b"a developer's database")
    monkeypatch.chdir(first)
    guard = _start_guard()
    monkeypatch.chdir(second)
    _finish_guard(guard)


def test_changing_directory_does_not_hide_a_write(tmp_path, monkeypatch) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    guard = _start_guard()
    (first / "gsd.db").write_bytes(b"written during the test")
    monkeypatch.chdir(second)
    with pytest.raises(pytest.fail.Exception, match="gsd.db") as failure:
        next(guard)
    assert str(first) in str(failure.value)
