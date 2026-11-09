from pathlib import Path

import pytest

from youtube_mp3_downloader import (
    DownloadFailure,
    build_ydl_options,
    classify_error,
    get_download_directory,
    normalize_mp3_volume,
    parse_video_url,
    validate_target_volume,
)


def test_parse_standard_video_url():
    value = "https://www.youtube.com/watch?v=abcdefghijk"
    assert parse_video_url(value) == value


def test_parse_video_url_with_playlist_parameter_stays_single_video_link():
    value = "https://www.youtube.com/watch?v=abcdefghijk&list=PL123456"
    assert parse_video_url(value) == value


def test_parse_short_url():
    assert parse_video_url("https://youtu.be/abcdefghijk") == "https://youtu.be/abcdefghijk"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/watch?v=abcdefghijk",
        "https://www.youtube.com/playlist?list=PL123456",
        "https://www.youtube.com/watch?v=too_short",
    ],
)
def test_reject_invalid_or_playlist_only_url(url):
    with pytest.raises(ValueError):
        parse_video_url(url)


def test_download_options_are_single_video_and_best_audio(tmp_path: Path):
    progress = lambda _data: None
    postprocessor = lambda _data: None
    options = build_ydl_options(tmp_path, "ffmpeg.exe", progress, postprocessor)

    assert options["noplaylist"] is True
    assert options["playlist_items"] == "1"
    assert options["format"] == "bestaudio/best"
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"
    assert options["postprocessors"][0]["preferredquality"] == "0"
    assert options["ffmpeg_location"] == "ffmpeg.exe"


def test_classify_ffmpeg_error_gives_specific_advice():
    label, advice = classify_error("ffmpeg binary not found")
    assert "FFmpeg" in label
    assert "最新版" in advice


def test_classify_network_error_gives_retry_advice():
    label, advice = classify_error("Connection timed out")
    assert "網路" in label
    assert "稍後" in advice


def test_download_folder_is_created_under_user_home_on_non_windows(monkeypatch, tmp_path):
    import youtube_mp3_downloader as app

    monkeypatch.setattr(app.os, "name", "posix")
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    folder = get_download_directory()
    assert folder == tmp_path / "Downloads"
    assert folder.is_dir()



@pytest.mark.parametrize("value, expected", [("89", 89.0), ("92.5", 92.5), (75, 75.0), (100, 100.0)])
def test_validate_target_volume_accepts_supported_values(value, expected):
    assert validate_target_volume(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "nan", "inf", 74.9, 100.1, -1])
def test_validate_target_volume_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_target_volume(value)


def test_mp3gain_normalization_uses_track_gain_and_clipping_protection(tmp_path, monkeypatch):
    import subprocess
    import youtube_mp3_downloader as app

    source = tmp_path / "歌曲.mp3"
    source.write_bytes(b"synthetic-mp3-data")
    fake_executable = tmp_path / "mp3gain.exe"
    fake_executable.write_bytes(b"fake executable")
    monkeypatch.setattr(app, "find_mp3gain_executable", lambda: fake_executable)

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="Track gain applied", stderr="")

    monkeypatch.setattr(app.subprocess, "run", fake_run)
    normalize_mp3_volume(source, 91.5)

    command = captured["command"]
    assert command[1:5] == ["-r", "-k", "-d", "2.50"]
    assert Path(command[-1]).name == "audio.mp3"
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL
    assert source.read_bytes() == b"synthetic-mp3-data"


def test_mp3gain_failure_does_not_overwrite_original_file(tmp_path, monkeypatch):
    import subprocess
    import youtube_mp3_downloader as app

    source = tmp_path / "original.mp3"
    original_bytes = b"keep-original-mp3"
    source.write_bytes(original_bytes)
    fake_executable = tmp_path / "mp3gain.exe"
    fake_executable.write_bytes(b"fake executable")
    monkeypatch.setattr(app, "find_mp3gain_executable", lambda: fake_executable)

    def failed_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="normalization failed")

    monkeypatch.setattr(app.subprocess, "run", failed_run)
    with pytest.raises(DownloadFailure, match="原始 MP3 未被覆寫"):
        normalize_mp3_volume(source, 89.0)

    assert source.read_bytes() == original_bytes
