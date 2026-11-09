# Third-party notices

## MP3Gain

This application bundles and invokes the MP3Gain Windows command-line backend (MP3Gain Windows stable package 1.2.5). MP3Gain is a separate third-party program; this project does not modify its source code.

- Upstream project: https://mp3gain.sourceforge.net/
- Official Windows downloads: https://mp3gain.sourceforge.net/download.php
- Corresponding command-line source archive listed by the upstream project: https://sourceforge.net/projects/mp3gain/files/
- License information for the 1.2.5 package: LGPL 2.1 (see the package license and the LGPL text at https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

The GitHub Actions workflow obtains the Windows command-line binary from the official MP3Gain SourceForge stable download area at build time. MP3Gain's own project page explains that the tool uses ReplayGain-style perceptual analysis and changes MP3 gain data without decoding and re-encoding the MP3: https://mp3gain.sourceforge.net/faq.php.

## Other components

- yt-dlp: see https://github.com/yt-dlp/yt-dlp and its included license.
- imageio-ffmpeg / FFmpeg: see https://github.com/imageio/imageio-ffmpeg and https://ffmpeg.org/legal.html.
- PyInstaller: see https://pyinstaller.org/ and its license.
