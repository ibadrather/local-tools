# local-tools

A collection of local-first tools, served over the LAN by a single Streamlit
app. Run it on one machine (a desktop, a NAS, a home server) and use it from
any browser on the network.

Tools so far:

- **Video compression** — re-encode a video with ffmpeg (libx265), keeping its
  original resolution and framerate.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- `ffmpeg` on the `PATH` **of the machine running the app** (`sudo apt install ffmpeg`)

## Run

```bash
uv sync
make app          # or: uv run streamlit run src/local_tools/app.py
```

`.streamlit/config.toml` binds the server to `0.0.0.0:8501`, so the app is
reachable from any machine on the network:

| From | URL |
| --- | --- |
| The machine itself | <http://localhost:8501> |
| Another machine | `http://<host-or-ip>:8501` |

Run `make app` from the repo root — that is where Streamlit picks up
`.streamlit/config.toml`.

### Opening the firewall

`ufw` is active on this machine, so port 8501 is blocked from other machines
until you allow it. Allow the local subnet only, not the whole internet:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8501 proto tcp
```

There is no authentication — put this on a trusted network only, and do not
forward the port through your router.

### Keeping it running

`make app` stops when you close the terminal. To keep it up across reboots,
run it under systemd as a user service, or inside `tmux`/`screen`.

## Paths are server-side

The browser sends a path; the **server** reads and writes it. So every path you
type belongs to the machine running the app, not to the laptop you are
browsing from. Each page names that host so it is unambiguous.

For the video tool you can enter either a full path to one video, or a folder —
in which case the videos inside it are offered in a picker, which is easier
than typing exact filenames for a remote machine.

Long encodes run inside the browser session: **keep the tab open until the job
finishes**, since closing it interrupts the encode.

## Compression levels

| Level | CRF | Notes |
| --- | --- | --- |
| Visually lossless | 18 | No visible loss, ~2-4x smaller. Default. |
| High quality | 22 | Good archival default, ~4-6x smaller. |
| Moderate | 28 | Smallest files, visible loss up close, ~6-10x smaller. |
| Truly lossless | — | Bit-exact `.mkv`; usually *larger* than an already-compressed source. |

A slower **preset** buys roughly 5-15% extra compression at the same quality,
at the cost of encoding time.

## Layout

```
.streamlit/config.toml            # network binding
src/local_tools/
├── app.py                        # entry point: st.navigation over every tool
├── ui.py                         # shared presentation helpers
└── tools/
    └── video_compression/
        ├── core.py               # ffmpeg wrapper - no Streamlit imports
        └── page.py               # Streamlit page - no encoding logic
```

Each tool keeps its logic in `core.py` and its interface in `page.py`, so the
logic stays usable from a script or a test.

## Adding a tool

1. Create `src/local_tools/tools/<name>/` with a `core.py` (the logic, no
   Streamlit imports) and a `page.py` exposing `render() -> None`.
2. Register it in `PAGES` in `src/local_tools/app.py`:

   ```python
   st.Page(render_my_tool, title="My tool", icon=":material/build:", url_path="my-tool")
   ```

Namespace the page's `st.session_state` keys (see `_key()` in
`video_compression/page.py`) — session state is shared across pages.

## Use as a library

```python
from pathlib import Path

from local_tools.tools.video_compression import CompressionLevel, compress_video

compress_video(
    Path("~/footage/clip.mp4"),
    output_path=Path("~/renders/clip.mp4"),
    compression_level=CompressionLevel.HIGH_QUALITY,
)
```

## Lint

```bash
make lint
```
