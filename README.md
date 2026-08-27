# local-tools

Small local-first utilities, with a Streamlit front end.

Currently: **video compression** — re-encode a video with ffmpeg (libx265),
keeping its original resolution and framerate.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- `ffmpeg` on your `PATH` (`sudo apt install ffmpeg`)

## Run

```bash
uv sync
make app          # or: uv run streamlit run src/local_tools/app.py
```

The app opens at <http://localhost:8501>. Paste the path to a video, pick a
compression level, and optionally override the output folder and file name —
leave those empty to write to `compressed/<name>_compressed.mp4` next to the
source.

## Compression levels

| Level | CRF | Notes |
| --- | --- | --- |
| Visually lossless | 18 | No visible loss, ~2-4x smaller. Default. |
| High quality | 22 | Good archival default, ~4-6x smaller. |
| Moderate | 28 | Smallest files, visible loss up close, ~6-10x smaller. |
| Truly lossless | — | Bit-exact `.mkv`; usually *larger* than an already-compressed source. |

A slower **preset** buys roughly 5-15% extra compression at the same quality,
at the cost of encoding time.

## Use as a library

```python
from pathlib import Path

from local_tools.compression import CompressionLevel, compress_video

compress_video(
    Path("~/footage/clip.mp4"),
    output_path=Path("~/renders/clip.mp4"),
    compression_level=CompressionLevel.HIGH_QUALITY,
)
```

## Layout

```
src/local_tools/
├── compression.py   # ffmpeg wrapper — no UI dependencies
└── app.py           # Streamlit UI — no encoding logic
```

## Lint

```bash
make lint
```
