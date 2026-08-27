"""Streamlit page for the video compressor.

Presentation only: every encode is delegated to
:mod:`local_tools.tools.video_compression.core`, which knows nothing about
Streamlit. Paths entered here are resolved on the machine running the server,
not on the visitor's computer, so the page says which host that is.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from local_tools.tools.video_compression.core import (
    PRESETS,
    CompressionError,
    CompressionLevel,
    compress_video,
    default_output_path,
    ffmpeg_path,
)
from local_tools.ui import format_duration, format_size, host_label

#: Levels in the order they are offered, best default first.
_LEVEL_LABELS: dict[CompressionLevel, str] = {
    CompressionLevel.VISUALLY_LOSSLESS: "Visually lossless - CRF 18, no visible loss (~2-4x smaller)",
    CompressionLevel.HIGH_QUALITY: "High quality - CRF 22, good archival default (~4-6x smaller)",
    CompressionLevel.MODERATE: "Moderate - CRF 28, smallest files (~6-10x smaller)",
    CompressionLevel.TRULY_LOSSLESS: "Truly lossless - bit-exact, often larger than the source",
}

#: Extensions offered when the input path points at a folder.
_VIDEO_SUFFIXES = frozenset({".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mts", ".webm", ".wmv"})

_AUDIO_BITRATES: tuple[str, ...] = ("96k", "128k", "192k", "256k")
_DEFAULT_PRESET = "medium"
_DEFAULT_AUDIO_BITRATE = "128k"

#: Prefix keeping this page's session-state keys out of other tools' way.
_KEY_PREFIX = "video_compression"

_LOG_LINES_SHOWN = 8


@dataclass(frozen=True)
class EncodingSettings:
    """The encoder options chosen in the sidebar."""

    level: CompressionLevel
    preset: str
    audio_bitrate: str
    overwrite: bool


@dataclass(frozen=True)
class CompressionResult:
    """Outcome of a completed encode, kept in session state across reruns."""

    output_path: Path
    input_size: int
    output_size: int
    elapsed_seconds: float


def render() -> None:
    """Render the video compression page."""
    st.title("Video compression")
    st.caption(
        f"Re-encode a video with ffmpeg (libx265), keeping its resolution and framerate. "
        f"Paths below are read and written on **{host_label()}**, the machine running this app."
    )

    if _ffmpeg_missing():
        return

    settings = _render_sidebar()
    input_path = _render_input_picker()

    if input_path is not None:
        output_path = _render_output_picker(input_path, settings)
        if st.button("Compress", type="primary"):
            _run_compression(input_path, output_path, settings)

    _render_outcome()


def _ffmpeg_missing() -> bool:
    """Show an install hint when ffmpeg is absent, and report whether it is."""
    if ffmpeg_path() is not None:
        return False

    st.error(
        f"ffmpeg was not found on {host_label()}. Install it there (`sudo apt install ffmpeg`) and reload this page."
    )
    return True


def _render_sidebar() -> EncodingSettings:
    """Render the encoder controls and return the current selection."""
    with st.sidebar:
        st.header("Encoding")
        level = st.selectbox(
            "Compression level",
            options=list(_LEVEL_LABELS),
            format_func=_level_label,
            key=_key("level"),
        )
        preset = st.selectbox(
            "Preset",
            options=PRESETS,
            index=PRESETS.index(_DEFAULT_PRESET),
            key=_key("preset"),
            help="Slower presets give ~5-15% smaller files at the same quality, but take much longer.",
        )
        audio_bitrate = st.selectbox(
            "Audio bitrate",
            options=_AUDIO_BITRATES,
            index=_AUDIO_BITRATES.index(_DEFAULT_AUDIO_BITRATE),
            key=_key("audio_bitrate"),
            disabled=level.is_lossless,
            help="Ignored for a truly lossless encode, where the audio track is copied as-is.",
        )
        overwrite = st.toggle("Overwrite existing output", key=_key("overwrite"))

    return EncodingSettings(level=level, preset=preset, audio_bitrate=audio_bitrate, overwrite=overwrite)


def _render_input_picker() -> Path | None:
    """Ask for a video on the server, and return it, or ``None`` if not usable yet.

    Accepts either a file or a folder. Typing a folder is the practical option
    over the network, where there is no tab completion: the videos inside it
    are then offered in a picker.
    """
    raw = st.text_input(
        "Input video or folder",
        key=_key("input_path"),
        placeholder="/mnt/media/footage   or   /mnt/media/footage/clip.mp4",
        help="Enter a folder to pick from the videos inside it, or the full path to one video.",
    )
    if not raw.strip():
        return None

    path = Path(raw.strip()).expanduser()

    if path.is_dir():
        chosen = _pick_video_in(path)
        if chosen is None:
            return None
        path = chosen
    elif not path.is_file():
        st.error(f"No such file or folder on {host_label()}: {path}")
        return None

    st.caption(f"Source: `{path}` - {format_size(path.stat().st_size)}")
    return path


def _pick_video_in(directory: Path) -> Path | None:
    """Offer the video files directly inside ``directory``, or explain why none are shown."""
    try:
        videos = sorted(item for item in directory.iterdir() if item.is_file() and _is_video(item))
    except OSError as exc:
        st.error(f"Cannot read that folder: {exc}")
        return None

    if not videos:
        st.warning(f"No video files directly inside {directory}")
        return None

    return st.selectbox("Video file", options=videos, format_func=_file_name, key=_key("input_file"))


def _render_output_picker(input_path: Path, settings: EncodingSettings) -> Path:
    """Ask where to write the result and return the resolved destination path."""
    suggested = default_output_path(input_path, settings.level)

    folder_column, name_column = st.columns(2)
    folder = folder_column.text_input(
        "Output folder",
        key=_key("output_folder"),
        placeholder=str(suggested.parent),
        help="Leave empty to use a `compressed/` folder next to the input. Created if missing.",
    )
    name = name_column.text_input(
        "Output file name",
        key=_key("output_name"),
        placeholder=suggested.name,
        help=f"Leave empty for the suggested name. Without an extension, `{settings.level.container_suffix}` is added.",
    )

    directory = Path(folder.strip()).expanduser() if folder.strip() else suggested.parent
    filename = name.strip() or suggested.name
    if not Path(filename).suffix:
        filename += settings.level.container_suffix

    output_path = directory / filename
    st.caption(f"Will write to: `{output_path}`")
    if output_path.exists() and not settings.overwrite:
        st.warning("That file already exists. Turn on 'Overwrite existing output' in the sidebar to replace it.")

    return output_path


def _run_compression(input_path: Path, output_path: Path, settings: EncodingSettings) -> None:
    """Encode the video, streaming ffmpeg's log, and store the outcome in session state."""
    log_lines: deque[str] = deque(maxlen=_LOG_LINES_SHOWN)

    with st.status("Compressing...", expanded=True) as status:
        st.caption("Keep this tab open until it finishes - closing it interrupts the encode.")
        log_area = st.empty()

        def append_log(line: str) -> None:
            log_lines.append(line)
            log_area.code("\n".join(log_lines), language=None)

        started = time.perf_counter()
        try:
            compress_video(
                input_path=input_path,
                output_path=output_path,
                compression_level=settings.level,
                preset=settings.preset,
                audio_bitrate=settings.audio_bitrate,
                overwrite=settings.overwrite,
                on_log=append_log,
            )
        except (CompressionError, FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
            status.update(label="Compression failed", state="error")
            st.session_state[_key("result")] = None
            st.session_state[_key("error")] = str(exc)
            return

        status.update(label="Compression complete", state="complete", expanded=False)

    st.session_state[_key("error")] = None
    st.session_state[_key("result")] = CompressionResult(
        output_path=output_path,
        input_size=input_path.stat().st_size,
        output_size=output_path.stat().st_size,
        elapsed_seconds=time.perf_counter() - started,
    )


def _render_outcome() -> None:
    """Show the result of the most recent run, if there is one."""
    error = st.session_state.get(_key("error"))
    if error:
        st.error(error)
        return

    result = st.session_state.get(_key("result"))
    if result is None:
        return

    st.success(f"Saved to `{result.output_path}` on {host_label()}")
    change = (result.output_size - result.input_size) / result.input_size if result.input_size else 0.0

    original_column, compressed_column, elapsed_column = st.columns(3)
    original_column.metric("Original", format_size(result.input_size))
    compressed_column.metric(
        "Compressed",
        format_size(result.output_size),
        delta=f"{change:+.0%}",
        delta_color="inverse",
    )
    elapsed_column.metric("Elapsed", format_duration(result.elapsed_seconds))


def _key(name: str) -> str:
    """Namespace a session-state key so tools cannot clash."""
    return f"{_KEY_PREFIX}.{name}"


def _level_label(level: CompressionLevel) -> str:
    """Return the human-readable label shown for a compression level."""
    return _LEVEL_LABELS[level]


def _file_name(path: Path) -> str:
    """Return just the file name, for the video picker's labels."""
    return path.name


def _is_video(path: Path) -> bool:
    """Whether a file looks like a video, judging by its extension."""
    return path.suffix.lower() in _VIDEO_SUFFIXES
