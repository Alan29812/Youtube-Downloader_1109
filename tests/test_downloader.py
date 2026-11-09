from pathlib import Path

import pytest

from youtube_mp3_downloader import (
    build_ydl_options,
    classify_error,
    get_download_directory,
    parse_video_url,
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
