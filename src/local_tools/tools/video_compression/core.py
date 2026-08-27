"""Compress a video using ffmpeg (libx265) while preserving resolution and fps.

This module holds the compression logic only: it has no user-interface
dependencies, so it can be driven from the Streamlit app in
:mod:`local_tools.app`, from a script, or from a test.

Example:
    >>> compress_video(Path("~/footage/DJI_0001.MP4"))  # doctest: +SKIP
    PosixPath('/home/me/footage/compressed/DJI_0001_compressed.mp4')
"""

from __future__ import annotations

import shutil
import subprocess
from collections import deque
from collections.abc import Callable, Iterator
from enum import Enum
from pathlib import Path
from typing import TextIO

FFMPEG_BINARY = "ffmpeg"

#: Directory created next to the source file when no output path is given.
DEFAULT_OUTPUT_DIRNAME = "compressed"

#: libx265 presets, ordered from best compression (slowest) to fastest.
PRESETS: tuple[str, ...] = (
    "veryslow",
    "slower",
    "slow",
    "medium",
    "fast",
    "faster",
    "veryfast",
    "superfast",
    "ultrafast",
)

#: Number of ffmpeg log lines kept to explain a failed encode.
_LOG_TAIL_SIZE = 20


class CompressionError(RuntimeError):
    """Raised when ffmpeg is unavailable or exits with a non-zero status."""


class CompressionLevel(Enum):
    """Quality/size tradeoff for the encode.

    All levels preserve the source resolution and framerate; only the codec
    parameters change. Numeric values are CRF (Constant Rate Factor) integers
    passed to libx265, except :attr:`TRULY_LOSSLESS` which is a sentinel that
    enables the encoder's mathematically-lossless mode.

    Attributes:
        TRULY_LOSSLESS: Bit-exact reconstruction. **Warning**: because DJI
            footage is already H.264-compressed, a lossless re-encode must
            preserve every existing pixel (and every existing compression
            artifact), so the output is typically the same size as the
            source or *larger*. Only useful if you plan to further edit
            the file without generation loss.
        VISUALLY_LOSSLESS: CRF 18. No perceptible difference from the source
            to the human eye, but real compression. Typical size reduction
            ~2-4x on DJI 4K footage. This is what most people mean by
            "lossless compression" in practice.
        HIGH_QUALITY: CRF 22. Very minor loss, usually invisible at normal
            viewing distances. Typical size reduction ~4-6x. Good archival
            default when disk space matters.
        MODERATE: CRF 28. Visible loss on close inspection but still decent
            on a 4K display. Typical size reduction ~6-10x.
    """

    TRULY_LOSSLESS = "lossless"
    VISUALLY_LOSSLESS = 18
    HIGH_QUALITY = 22
    MODERATE = 28

    @property
    def is_lossless(self) -> bool:
        """Whether this level enables libx265's mathematically-lossless mode."""
        return self is CompressionLevel.TRULY_LOSSLESS

    @property
    def container_suffix(self) -> str:
        """Preferred output extension for this level.

        Matroska (``.mkv``) is a more permissive container for lossless HEVC;
        some players and muxers reject lossless HEVC inside ``.mp4``.
        """
        return ".mkv" if self.is_lossless else ".mp4"


def ffmpeg_path() -> str | None:
    """Return the resolved path to the ffmpeg executable, or ``None`` if missing."""
    return shutil.which(FFMPEG_BINARY)


def default_output_path(input_path: Path, compression_level: CompressionLevel) -> Path:
    """Return the output path used when the caller does not supply one.

    Args:
        input_path: Path to the source video file.
        compression_level: Level whose container suffix decides the extension.

    Returns:
        ``<input_parent>/compressed/<stem>_compressed<suffix>``. The directory
        is not created here.
    """
    input_path = Path(input_path).expanduser()
    filename = f"{input_path.stem}_compressed{compression_level.container_suffix}"
    return input_path.parent / DEFAULT_OUTPUT_DIRNAME / filename


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    compression_level: CompressionLevel,
    preset: str,
    audio_bitrate: str,
    *,
    overwrite: bool,
) -> list[str]:
    """Assemble the ffmpeg argument list for a single encode.

    Args:
        input_path: Source video file.
        output_path: Destination video file.
        compression_level: Quality/size tradeoff. See :class:`CompressionLevel`.
        preset: libx265 preset, one of :data:`PRESETS`.
        audio_bitrate: Target AAC bitrate, ignored for lossless encodes.
        overwrite: Whether ffmpeg may replace an existing output file.

    Returns:
        The command as a list of arguments, ready for :mod:`subprocess`.
    """
    if compression_level.is_lossless:
        video_args = ["-c:v", "libx265", "-x265-params", "lossless=1"]
        audio_args = ["-c:a", "copy"]  # don't degrade audio in a lossless encode
    else:
        crf = int(compression_level.value)
        video_args = ["-c:v", "libx265", "-crf", str(crf)]
        audio_args = ["-c:a", "aac", "-b:a", audio_bitrate]

    return [
        FFMPEG_BINARY,
        "-y" if overwrite else "-n",
        "-i",
        str(input_path),
        *video_args,
        "-preset",
        preset,
        *audio_args,
        str(output_path),
    ]


def compress_video(
    input_path: Path,
    output_path: Path | None = None,
    compression_level: CompressionLevel = CompressionLevel.VISUALLY_LOSSLESS,
    preset: str = "medium",
    audio_bitrate: str = "128k",
    *,
    overwrite: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> Path:
    """Compress a video file with libx265, preserving resolution and fps.

    Resolution and framerate of the source are left untouched; audio is
    re-encoded to AAC (or copied, if :attr:`CompressionLevel.TRULY_LOSSLESS`
    is selected) and video is re-encoded with libx265.

    Args:
        input_path: Path to the source video file. Must exist.
        output_path: Destination file. Missing parent directories are created.
            Defaults to :func:`default_output_path`, i.e.
            ``<input_parent>/compressed/<stem>_compressed<suffix>``.
        compression_level: Quality/size tradeoff. See :class:`CompressionLevel`
            for guidance. Defaults to
            :attr:`CompressionLevel.VISUALLY_LOSSLESS` (CRF 18) — no
            perceptible quality loss with real size reduction.
        preset: libx265 preset controlling encoder speed vs. compression
            efficiency; see :data:`PRESETS`. Slower presets produce ~5-15%
            smaller files at the same quality but take significantly longer
            to encode. Defaults to ``"medium"``.
        audio_bitrate: Target AAC audio bitrate (e.g. ``"128k"``, ``"96k"``).
            Ignored when ``compression_level`` is
            :attr:`CompressionLevel.TRULY_LOSSLESS` (audio is copied instead).
            Defaults to ``"128k"``.
        overwrite: If ``True``, overwrite the output file if it already
            exists. If ``False`` and the output exists, raise
            :class:`FileExistsError`. Defaults to ``False``.
        on_log: Optional callback invoked with each line ffmpeg writes to
            stderr, for live progress reporting. Defaults to ``None``.

    Returns:
        The absolute path to the newly created compressed video file.

    Raises:
        FileNotFoundError: If ``input_path`` does not exist or is not a file.
        FileExistsError: If the output file already exists and ``overwrite``
            is ``False``.
        ValueError: If the output path would overwrite the input file.
        CompressionError: If ffmpeg is not installed or the encode fails.
    """
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    if ffmpeg_path() is None:
        raise CompressionError(f"'{FFMPEG_BINARY}' was not found on PATH. Install ffmpeg and try again.")

    if output_path is None:
        output_path = default_output_path(input_path, compression_level)
    output_path = Path(output_path).expanduser().resolve()

    if output_path == input_path:
        raise ValueError(f"Output path must differ from the input file: {input_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}. Enable overwrite to replace it.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_ffmpeg_command(
        input_path=input_path,
        output_path=output_path,
        compression_level=compression_level,
        preset=preset,
        audio_bitrate=audio_bitrate,
        overwrite=overwrite,
    )

    log_tail: deque[str] = deque(maxlen=_LOG_TAIL_SIZE)
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) as process:
        for line in _iter_output_lines(process.stderr):
            log_tail.append(line)
            if on_log is not None:
                on_log(line)

    if process.returncode != 0:
        details = "\n".join(log_tail)
        raise CompressionError(f"ffmpeg exited with status {process.returncode}:\n{details}")

    return output_path


def _iter_output_lines(stream: TextIO | None) -> Iterator[str]:
    """Yield non-empty lines from an ffmpeg output stream as they arrive.

    ffmpeg separates its periodic progress stats with carriage returns so a
    terminal overwrites a single line; iterating the stream with a plain
    ``for line in stream`` would therefore yield nothing until the encode
    finished. Splitting on both terminators keeps the output live.

    Args:
        stream: The pipe to read, or ``None`` if it was never opened.

    Yields:
        Stripped output lines, in order.
    """
    if stream is None:
        return

    buffer = ""
    while char := stream.read(1):
        if char in {"\n", "\r"}:
            if buffer.strip():
                yield buffer.strip()
            buffer = ""
        else:
            buffer += char

    if buffer.strip():
        yield buffer.strip()
