from __future__ import annotations

import argparse
import ctypes
import os
import queue
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp
import tkinter as tk
from tkinter import ttk


APP_TITLE = "YouTube MP3 Downloader"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


class DownloadFailure(RuntimeError):
    """A user-facing download or conversion failure."""


def parse_video_url(value: str) -> str:
    """Validate a single-video YouTube URL; playlist-only URLs are rejected."""
    raw = value.strip()
    if not raw:
        raise ValueError("請先貼上 YouTube 影片網址。")

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if host not in SUPPORTED_HOSTS:
        raise ValueError("網址不是受支援的 YouTube 網址。請使用 youtube.com 或 youtu.be 的影片連結。")

    video_id = ""
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
            video_id = parts[1]

    if not VIDEO_ID_RE.fullmatch(video_id or ""):
        raise ValueError("找不到有效的影片 ID。請複製單支影片的完整網址，而不是播放清單網址。")

    # Preserve the video URL/query parameters. yt-dlp is also explicitly
    # configured with noplaylist=True, so a list= parameter is ignored.
    return candidate


def get_download_directory(create: bool = True) -> Path:
    """Return the current user's Windows Downloads known folder when possible."""
    downloads: Path | None = None

    if os.name == "nt":
        # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
        try:
            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_uint32),
                    ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            folder_guid = GUID.from_buffer_copy(
                uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le
            )
            path_pointer = ctypes.c_void_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_guid), 0, None, ctypes.byref(path_pointer)
            )
            if result == 0 and path_pointer.value:
                downloads = Path(ctypes.wstring_at(path_pointer.value))
                ctypes.windll.ole32.CoTaskMemFree(path_pointer)
        except (AttributeError, OSError, TypeError, ValueError):
            downloads = None

    if downloads is None:
        profile = os.environ.get("USERPROFILE")
        downloads = (Path(profile) if profile else Path.home()) / "Downloads"

    if create:
        downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def classify_error(error: BaseException | str) -> tuple[str, str]:
    """Map common network/YouTube/FFmpeg errors to actionable guidance."""
    message = str(error)
    lowered = message.lower()

    if any(word in lowered for word in ("ffmpeg", "ffprobe", "postprocessing", "post-processing")):
        return (
            "音訊轉換失敗（FFmpeg）",
            "請重新下載最新版程式；若仍失敗，確認防毒軟體沒有隔離程式內的 FFmpeg 元件。",
        )
    if any(word in lowered for word in ("timed out", "timeout", "connection", "network", "name or service not known", "urlopen")):
        return (
            "網路連線失敗",
            "請確認網路正常、沒有阻擋 YouTube，稍後再試；必要時可更換網路或關閉造成干擾的 VPN/Proxy。",
        )
    if any(word in lowered for word in ("private video", "video unavailable", "not available", "members-only", "geo-restricted", "sign in")):
        return (
            "影片無法存取",
            "請確認影片仍可播放、沒有私人/會員/地區限制。此程式不會繞過登入、付費或存取限制。",
        )
    if any(word in lowered for word in ("unsupported url", "not a valid url", "invalid url")):
        return (
            "影片網址格式錯誤",
            "請從 YouTube 的單支影片頁面複製網址，例如 https://www.youtube.com/watch?v=xxxxxxxxxxx。",
        )
    if any(word in lowered for word in ("permission denied", "access is denied", "winerror 5")):
        return (
            "沒有資料夾寫入權限",
            "請確認 Windows「下載」資料夾可寫入，並檢查防毒軟體或資料夾存取控制設定。",
        )
    if any(word in lowered for word in ("http error 403", "http error 429", "too many requests", "rate-limit")):
        return (
            "YouTube 暫時拒絕請求",
            "請稍候再試，避免短時間連續下載；並確認程式為最新版。",
        )
    return (
        "下載或轉換失敗",
        "請確認影片可正常播放、網路連線正常，並更新至最新版程式。詳細錯誤已顯示在下方。",
    )


def build_ydl_options(
    download_dir: Path,
    ffmpeg_path: str,
    progress_hook,
    postprocessor_hook,
) -> dict[str, Any]:
    """Create yt-dlp options for best audio, MP3 VBR 0 and single-video mode."""
    return {
        "format": "bestaudio/best",
        "noplaylist": True,
        "playlist_items": "1",
        "outtmpl": str(download_dir / "%(title).180B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "overwrites": False,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_path,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
    }


def download_video_as_mp3(
    url: str,
    progress_callback,
    status_callback,
) -> tuple[Path, str]:
    """Download one authorized video and return its MP3 path and title."""
    validated_url = parse_video_url(url)
    download_dir = get_download_directory()
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        raise DownloadFailure("找不到 FFmpeg 執行檔。")

    def on_progress(data: dict[str, Any]) -> None:
        state = data.get("status")
        if state == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            if total:
                percent = max(0.0, min(94.0, downloaded / total * 94.0))
                progress_callback(
                    percent,
                    f"下載中… {downloaded / total * 100:.1f}%",
                )
            else:
                progress_callback(0.0, "下載中…")
        elif state == "finished":
            progress_callback(95.0, "下載完成，正在轉換 MP3…")

    def on_postprocessor(data: dict[str, Any]) -> None:
        state = data.get("status")
        if state == "started":
            progress_callback(96.0, "正在轉換 MP3（保留來源取樣率設定）…")
        elif state == "finished":
            progress_callback(99.0, "MP3 轉換完成，正在確認檔案…")

    options = build_ydl_options(download_dir, ffmpeg_path, on_progress, on_postprocessor)
    status_callback("正在連線並取得影片資訊…")

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(validated_url, download=True)
            if not info:
                raise DownloadFailure("YouTube 沒有回傳影片資訊。")
            # prepare_filename uses the original media extension. FFmpegExtractAudio
            # replaces that extension with .mp3 after successful conversion.
            original_path = Path(downloader.prepare_filename(info))
            expected_mp3 = original_path.with_suffix(".mp3")
            if not expected_mp3.is_file():
                video_id = str(info.get("id", ""))
                matches = list(download_dir.glob(f"* [{video_id}].mp3")) if video_id else []
                if matches:
                    expected_mp3 = matches[0]
                else:
                    raise DownloadFailure(
                        f"轉換程序結束，但找不到輸出的 MP3 檔案。預期位置：{expected_mp3}"
                    )
            return expected_mp3, str(info.get("title") or expected_mp3.stem)
    except DownloadFailure:
        raise
    except Exception as exc:
        label, suggestion = classify_error(exc)
        raise DownloadFailure(f"{label}\n建議：{suggestion}\n詳細錯誤：{exc}") from exc


class DownloaderApp:
    BG = "#0b1220"
    PANEL = "#121d30"
    PANEL_LIGHT = "#192840"
    TEXT = "#edf4ff"
    MUTED = "#91a3bd"
    ACCENT = "#36c8d4"
    SUCCESS = "#61d69a"
    ERROR = "#ff8f8f"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.worker: threading.Thread | None = None

        root.title(APP_TITLE)
        root.geometry("760x570")
        root.minsize(680, 520)
        root.configure(bg=self.BG)
        root.resizable(True, True)

        self._configure_styles()
        self._build_ui()
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=self.PANEL, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("PanelMuted.TLabel", background=self.PANEL, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 23, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure(
            "Accent.TButton",
            background=self.ACCENT,
            foreground="#07131f",
            font=("Segoe UI", 10, "bold"),
            padding=(18, 11),
            borderwidth=0,
        )
        style.map("Accent.TButton", background=[("disabled", "#526778"), ("active", "#62dce4")])
        style.configure(
            "Secondary.TButton",
            background=self.PANEL_LIGHT,
            foreground=self.TEXT,
            font=("Segoe UI", 9, "bold"),
            padding=(12, 9),
            borderwidth=0,
        )
        style.map("Secondary.TButton", background=[("active", "#243853")])
        style.configure(
            "Download.Horizontal.TProgressbar",
            troughcolor=self.PANEL_LIGHT,
            background=self.ACCENT,
            bordercolor=self.PANEL_LIGHT,
            lightcolor=self.ACCENT,
            darkcolor=self.ACCENT,
            thickness=13,
        )
        style.configure(
            "Url.TEntry",
            fieldbackground="#0c1728",
            foreground=self.TEXT,
            insertcolor=self.TEXT,
            bordercolor="#2a3b54",
            lightcolor="#2a3b54",
            darkcolor="#2a3b54",
            padding=12,
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(30, 25, 30, 22))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 22))
        ttk.Label(header, text="AUDIO  /  DOWNLOADER", foreground=self.ACCENT, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(header, text="YouTube MP3", style="Title.TLabel").pack(anchor="w", pady=(5, 2))
        ttk.Label(
            header,
            text="貼上單支影片連結，自動擷取音訊並儲存到 Windows「下載」資料夾。",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        card = ttk.Frame(outer, style="Panel.TFrame", padding=22)
        card.pack(fill="x")
        ttk.Label(card, text="影片連結", style="Panel.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            card,
            text="支援 YouTube 影片、Shorts、直播回放與 youtu.be 短網址。",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(4, 13))

        entry_row = ttk.Frame(card, style="Panel.TFrame")
        entry_row.pack(fill="x")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(entry_row, textvariable=self.url_var, style="Url.TEntry", font=("Segoe UI", 10))
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<<Paste>>", self._on_paste_event)
        self.url_entry.bind("<Control-v>", self._on_paste_event)
        self.url_entry.bind("<Return>", lambda _event: self.start_download())

        self.paste_button = ttk.Button(entry_row, text="貼上", style="Secondary.TButton", command=self.paste_from_clipboard)
        self.paste_button.pack(side="left", padx=(9, 0))

        self.download_button = ttk.Button(
            card, text="↓  下載 MP3", style="Accent.TButton", command=self.start_download
        )
        self.download_button.pack(fill="x", pady=(14, 0))

        status_card = ttk.Frame(outer, style="Panel.TFrame", padding=20)
        status_card.pack(fill="x", pady=(16, 0))
        status_top = ttk.Frame(status_card, style="Panel.TFrame")
        status_top.pack(fill="x")
        ttk.Label(status_top, text="下載狀態", style="Panel.TLabel", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.percent_label = ttk.Label(status_top, text="0%", style="PanelMuted.TLabel")
        self.percent_label.pack(side="right")
        self.progress = ttk.Progressbar(
            status_card, style="Download.Horizontal.TProgressbar", maximum=100, value=0
        )
        self.progress.pack(fill="x", pady=(12, 9))
        self.status_var = tk.StringVar(value="等待貼上 YouTube 影片連結")
        self.status_label = ttk.Label(status_card, textvariable=self.status_var, style="PanelMuted.TLabel")
        self.status_label.pack(anchor="w")

        details = ttk.Frame(outer)
        details.pack(fill="x", pady=(16, 0))
        ttk.Label(details, text="訊息紀錄", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 7))
        self.log = tk.Text(
            details,
            height=5,
            wrap="word",
            bg="#0c1728",
            fg=self.MUTED,
            insertbackground=self.TEXT,
            relief="flat",
            padx=12,
            pady=9,
            font=("Consolas", 9),
            state="disabled",
        )
        self.log.pack(fill="x")
        self.log.tag_configure("success", foreground=self.SUCCESS)
        self.log.tag_configure("error", foreground=self.ERROR)
        self.log.tag_configure("normal", foreground=self.MUTED)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(13, 0))
        ttk.Label(
            footer,
            text="輸出位置：Windows 使用者的「下載」資料夾  ·  MP3 VBR 0",
            style="Muted.TLabel",
        ).pack(side="left")
        self.open_button = ttk.Button(footer, text="開啟下載資料夾", style="Secondary.TButton", command=self.open_download_folder)
        self.open_button.pack(side="right")

        ttk.Label(
            outer,
            text="請僅下載你擁有或已取得授權的內容。MP3 為有損格式，轉檔不會提升來源音質。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(13, 0))

        self._append_log("準備就緒。貼上影片網址即可自動開始下載。")
        self.url_entry.focus_set()

    def _append_log(self, message: str, tag: str = "normal") -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_paste_event(self, _event=None) -> None:
        self.root.after(300, self._auto_start_if_valid)

    def _auto_start_if_valid(self) -> None:
        if self.busy:
            return
        try:
            parse_video_url(self.url_var.get())
        except ValueError:
            return
        self.start_download()

    def paste_from_clipboard(self) -> None:
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            self.status_var.set("剪貼簿沒有可用的文字連結")
            return
        self.url_var.set(text)
        self.start_download()

    def start_download(self) -> None:
        if self.busy:
            return
        try:
            url = parse_video_url(self.url_var.get())
        except ValueError as exc:
            self.status_var.set(str(exc))
            self._append_log(str(exc), "error")
            return

        self.busy = True
        self.download_button.configure(state="disabled")
        self.paste_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.percent_label.configure(text="0%")
        self.status_var.set("正在準備下載…")
        self._append_log("開始處理單支影片…")

        self.worker = threading.Thread(target=self._download_worker, args=(url,), daemon=True)
        self.worker.start()

    def _download_worker(self, url: str) -> None:
        try:
            path, title = download_video_as_mp3(
                url,
                lambda value, message: self.events.put(("progress", (value, message))),
                lambda message: self.events.put(("status", message)),
            )
            self.events.put(("success", (path, title)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    value, message = payload
                    self.progress.configure(value=value)
                    self.percent_label.configure(text=f"{int(value)}%")
                    self.status_var.set(message)
                elif event == "status":
                    self.status_var.set(payload)
                elif event == "success":
                    path, title = payload
                    self.busy = False
                    self.download_button.configure(state="normal")
                    self.paste_button.configure(state="normal")
                    self.progress.configure(value=100)
                    self.percent_label.configure(text="100%")
                    self.status_var.set("下載成功！MP3 已儲存。")
                    self._append_log(f"成功：{title}", "success")
                    self._append_log(f"檔案：{path}", "success")
                elif event == "error":
                    self.busy = False
                    self.download_button.configure(state="normal")
                    self.paste_button.configure(state="normal")
                    self.status_var.set("下載失敗，請查看下方錯誤與建議。")
                    self._append_log(payload, "error")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def open_download_folder(self) -> None:
        folder = get_download_directory()
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            self._append_log(f"無法開啟資料夾：{exc}", "error")

    def run(self) -> None:
        self.root.mainloop()


def self_test() -> int:
    """Smoke-test the packaged runtime without opening the graphical interface."""
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if not ffmpeg or not Path(ffmpeg).is_file():
            return 2
        # Ensure yt-dlp and the MP3 postprocessor are importable in a frozen build.
        if not hasattr(yt_dlp, "YoutubeDL"):
            return 3
        options = build_ydl_options(Path.cwd(), ffmpeg, lambda *_: None, lambda *_: None)
        if options.get("noplaylist") is not True:
            return 4
        return 0
    except Exception:
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    root = tk.Tk()
    app = DownloaderApp(root)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
