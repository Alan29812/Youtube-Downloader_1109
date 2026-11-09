# YouTube MP3 Downloader

A Windows desktop GUI for saving the audio from **a single YouTube video** as an MP3 file.

> Use this application only for videos you own, content in the public domain, or content you are otherwise authorized to download. Respect copyright and the platform's terms.

## Features

- Paste a single YouTube video URL to start automatically, or enter a URL and press **Download MP3**.
- Explicit single-video mode (`noplaylist=True`): a `list=` parameter never triggers a playlist download.
- Downloads the best available audio stream and converts it to MP3 with FFmpeg at VBR quality 0.
- Does not force a new sample rate during conversion; FFmpeg keeps the decoded input sample rate unless the source/encoder requires otherwise. MP3 is a lossy format, so conversion cannot restore quality that was not in the source.
- Automatically applies MP3Gain **Track Gain** after conversion. Each song is normalized independently to the manually entered target volume (default **89.0 dB**, allowed range 75–100 dB).
- Uses MP3Gain clipping protection. If a track cannot safely reach the requested target without clipping, MP3Gain reduces the applied gain to a safe level.
- MP3Gain changes MP3 frame gain directly; it does not decode and re-encode the MP3 during normalization.
- Live download progress, conversion and normalization status, readable errors, and suggested fixes.
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

FFmpeg is supplied by the `imageio-ffmpeg` package. The Windows executable also bundles the MP3Gain command-line backend. When running from source on Windows, place the official `mp3gain.exe` in the `vendor` directory before starting the application. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Build locally on Windows

```powershell
pip install -r requirements.txt
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name YouTube_MP3 --add-binary "vendor/mp3gain.exe;." --collect-data yt_dlp --collect-submodules yt_dlp.extractor --collect-submodules yt_dlp.postprocessor --collect-all imageio_ffmpeg youtube_mp3_downloader.py
.\dist\YouTube_MP3.exe
```

## Validation

```powershell
pip install -r requirements.txt pytest
pytest -q
python youtube_mp3_downloader.py --self-test
```

GitHub Actions downloads the official MP3Gain Windows command-line package, runs the unit test suite, packages the application on Windows, and performs a frozen-executable smoke test that creates a synthetic MP3 and actually runs MP3Gain on it. This validates the bundled FFmpeg and MP3Gain components without downloading a real YouTube video.
