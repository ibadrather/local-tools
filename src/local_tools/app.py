"""Streamlit front end for the video compressor.

This module is the presentation layer only: every encode is delegated to
:mod:`local_tools.compression`, which knows nothing about Streamlit.

Run it with::

    uv run streamlit run src/local_tools/app.py
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from local_tools.compression import (
    PRESETS,
    CompressionError,
    CompressionLevel,
    compress_video,
    default_output_path,
    ffmpeg_path,
)

#: Levels in the order they are offered, best default first.
_LEVEL_LABELS: dict[CompressionLevel, str] = {
    CompressionLevel.VISUALLY_LOSSLESS: "Visually lossless - CRF 18, no visible loss (~2-4x smaller)",
    CompressionLevel.HIGH_QUALITY: "High quality - CRF 22, good archival default (~4-6x smaller)",
    CompressionLevel.MODERATE: "Moderate - CRF 28, smallest files (~6-10x smaller)",
    CompressionLevel.TRULY_LOSSLESS: "Truly lossless - bit-exact, often larger than the source",
}

_AUDIO_BITRATES: tuple[str, ...] = ("96k", "128k", "192k", "256k")
_DEFAULT_PRESET = "medium"
_DEFAULT_AUDIO_BITRATE = "128k"

#: ``st.session_state`` keys holding the outcome of the most recent run.
_RESULT_KEY = "compression_result"
_ERROR_KEY = "compression_error"

_LOG_LINES_SHOWN = 8
_BYTES_PER_UNIT = 1024


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


def main() -> None:
    """Render the page."""
    st.set_page_config(page_title="Video Compressor", page_icon=":clapper:", layout="centered")
    st.title("Video compressor")
    st.caption("Re-encode a video with ffmpeg (libx265), keeping its original resolution and framerate.")

    if ffmpeg_path() is None:
        st.error("ffmpeg was not found on PATH. Install it (`sudo apt install ffmpeg`) and reload this page.")
        st.stop()

    settings = _render_sidebar()
    input_path = _render_input_picker()

    if input_path is not None:
        output_path = _render_output_picker(input_path, settings)
        if st.button("Compress", type="primary"):
            _run_compression(input_path, output_path, settings)

    _render_outcome()


def _render_sidebar() -> EncodingSettings:
    """Render the encoder controls and return the current selection."""
    with st.sidebar:
        st.header("Encoding")
        level = st.selectbox(
            "Compression level",
            options=list(_LEVEL_LABELS),
            format_func=_level_label,
            key="level",
        )
        preset = st.selectbox(
            "Preset",
            options=PRESETS,
            index=PRESETS.index(_DEFAULT_PRESET),
            key="preset",
            help="Slower presets give ~5-15% smaller files at the same quality, but take much longer.",
        )
        audio_bitrate = st.selectbox(
            "Audio bitrate",
            options=_AUDIO_BITRATES,
            index=_AUDIO_BITRATES.index(_DEFAULT_AUDIO_BITRATE),
            key="audio_bitrate",
            disabled=level.is_lossless,
            help="Ignored for a truly lossless encode, where the audio track is copied as-is.",
        )
        overwrite = st.toggle("Overwrite existing output", key="overwrite")

    return EncodingSettings(level=level, preset=preset, audio_bitrate=audio_bitrate, overwrite=overwrite)


def _render_input_picker() -> Path | None:
    """Ask for the source video and return it, or ``None`` if it is not usable yet."""
    raw = st.text_input("Input video", key="input_path", placeholder="/home/me/footage/clip.mp4")
    if not raw.strip():
        return None

    path = Path(raw.strip()).expanduser()
    if not path.is_file():
        st.error(f"Not a file: {path}")
        return None

    st.caption(f"Source size: {_format_size(path.stat().st_size)}")
    return path


def _render_output_picker(input_path: Path, settings: EncodingSettings) -> Path:
    """Ask where to write the result and return the resolved destination path."""
    suggested = default_output_path(input_path, settings.level)

    folder_column, name_column = st.columns(2)
    folder = folder_column.text_input(
        "Output folder",
        key="output_folder",
        placeholder=str(suggested.parent),
        help="Leave empty to use a `compressed/` folder next to the input. Created if missing.",
    )
    name = name_column.text_input(
        "Output file name",
        key="output_name",
        placeholder=suggested.name,
        help=f"Leave empty for the suggested name. Without an extension, `{settings.level.container_suffix}` is added.",
    )

    directory = Path(folder.strip()).expanduser() if folder.strip() else suggested.parent
    filename = name.strip() or suggested.name
    if not Path(filename).suffix:
        filename += settings.level.container_suffix

    output_path = directory / filename
    st.caption(f"Will write to: {output_path}")
    if output_path.exists() and not settings.overwrite:
        st.warning("That file already exists. Turn on 'Overwrite existing output' in the sidebar to replace it.")

    return output_path


def _run_compression(input_path: Path, output_path: Path, settings: EncodingSettings) -> None:
    """Encode the video, streaming ffmpeg's log, and store the outcome in session state."""
    log_lines: deque[str] = deque(maxlen=_LOG_LINES_SHOWN)

    with st.status("Compressing...", expanded=True) as status:
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
            st.session_state[_RESULT_KEY] = None
            st.session_state[_ERROR_KEY] = str(exc)
            return

        status.update(label="Compression complete", state="complete", expanded=False)

    st.session_state[_ERROR_KEY] = None
    st.session_state[_RESULT_KEY] = CompressionResult(
        output_path=output_path,
        input_size=input_path.stat().st_size,
        output_size=output_path.stat().st_size,
        elapsed_seconds=time.perf_counter() - started,
    )


def _render_outcome() -> None:
    """Show the result of the most recent run, if there is one."""
    error = st.session_state.get(_ERROR_KEY)
    if error:
        st.error(error)
        return

    result = st.session_state.get(_RESULT_KEY)
    if result is None:
        return

    st.success(f"Saved to {result.output_path}")
    change = (result.output_size - result.input_size) / result.input_size if result.input_size else 0.0

    original_column, compressed_column, elapsed_column = st.columns(3)
    original_column.metric("Original", _format_size(result.input_size))
    compressed_column.metric(
        "Compressed",
        _format_size(result.output_size),
        delta=f"{change:+.0%}",
        delta_color="inverse",
    )
    elapsed_column.metric("Elapsed", _format_duration(result.elapsed_seconds))


def _level_label(level: CompressionLevel) -> str:
    """Return the human-readable label shown for a compression level."""
    return _LEVEL_LABELS[level]


def _format_size(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < _BYTES_PER_UNIT:
            return f"{size:,.1f} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{size:,.1f} GB"


def _format_duration(seconds: float) -> str:
    """Render a duration in seconds as ``1m 05s``."""
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"


if __name__ == "__main__":
    main()
