# YouTube MP3 Downloader

A Windows desktop GUI for saving the audio from **a single YouTube video** as an MP3 file.

> Use this application only for videos you own, content in the public domain, or content you are otherwise authorized to download. Respect copyright and the platform's terms.

## Features

- Paste a single YouTube video URL to start automatically, or enter a URL and press **Download MP3**.
- Explicit single-video mode (`noplaylist=True`): a `list=` parameter never triggers a playlist download.
- Downloads the best available audio stream and converts it to MP3 with FFmpeg at VBR quality 0.
- Does not force a new sample rate during conversion; FFmpeg keeps the decoded input sample rate unless the source/encoder requires otherwise. MP3 is a lossy format, so conversion cannot restore quality that was not in the source.
- Live download progress, conversion status, readable errors, and suggested fixes.
- Saves completed MP3 files to the current Windows user's Downloads folder.
- Bundled FFmpeg and a one-file Windows executable are produced by GitHub Actions.

## Download the Windows executable

1. Open this repository's **Actions** tab.
2. Select the latest successful **Build Windows executable** run.
3. Under **Artifacts**, download `YouTube-MP3-Windows`.
4. Extract the ZIP and double-click `YouTube_MP3.exe`.

Windows may show a SmartScreen warning because the executable is not code-signed. Only run a build you trust and downloaded from this repository.

## Run from source

Python 3.10+ is recommended.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python youtube_mp3_downloader.py
```

FFmpeg is supplied by the `imageio-ffmpeg` package.

## Build locally on Windows

```powershell
pip install -r requirements.txt
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name YouTube_MP3 --collect-data yt_dlp --collect-submodules yt_dlp.extractor --collect-submodules yt_dlp.postprocessor --collect-all imageio_ffmpeg youtube_mp3_downloader.py
.\dist\YouTube_MP3.exe
```

## Validation

```powershell
pip install -r requirements.txt pytest
pytest -q
python youtube_mp3_downloader.py --self-test
```

GitHub Actions runs the test suite, packages the application on Windows, and performs a frozen-executable smoke test on every push and manual workflow run.
