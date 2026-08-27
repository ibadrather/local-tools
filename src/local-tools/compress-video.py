"""Compress a video using ffmpeg (libx265) while preserving resolution and fps.

The compressed file is written to a ``compressed/`` folder that sits next to
the input file (i.e. inside the input's parent directory). The output file
keeps the original stem with a ``_compressed`` suffix and a ``.mp4`` or
``.mkv`` extension depending on the selected mode.

Example:
    Input:  /home/me/footage/DJI_0001.MP4
    Output: /home/me/footage/compressed/DJI_0001_compressed.mp4
"""

from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path


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


def compress_video(
    input_path: Path,
    compression_level: CompressionLevel = CompressionLevel.VISUALLY_LOSSLESS,
    preset: str = "medium",
    audio_bitrate: str = "128k",
    overwrite: bool = False,
) -> Path:
    """Compress a video file with libx265, preserving resolution and fps.

    The output is written to ``<input_parent>/compressed/<stem>_compressed.<ext>``.
    The ``compressed`` directory is created if it does not already exist.
    Resolution and framerate of the source are left untouched; audio is
    re-encoded to AAC (or copied, if :attr:`CompressionLevel.TRULY_LOSSLESS`
    is selected) and video is re-encoded with libx265.

    Args:
        input_path: Path to the source video file. Must exist.
        compression_level: Quality/size tradeoff. See :class:`CompressionLevel`
            for guidance. Defaults to
            :attr:`CompressionLevel.VISUALLY_LOSSLESS` (CRF 18) — no
            perceptible quality loss with real size reduction.
        preset: libx265 preset controlling encoder speed vs. compression
            efficiency. Valid values (slowest -> fastest compression):
            ``veryslow``, ``slower``, ``slow``, ``medium``, ``fast``,
            ``faster``, ``veryfast``, ``superfast``, ``ultrafast``.
            Slower presets produce ~5-15% smaller files at the same quality
            but take significantly longer to encode. Defaults to ``"medium"``.
        audio_bitrate: Target AAC audio bitrate (e.g. ``"128k"``, ``"96k"``).
            Ignored when ``compression_level`` is
            :attr:`CompressionLevel.TRULY_LOSSLESS` (audio is copied instead).
            Defaults to ``"128k"``.
        overwrite: If ``True``, overwrite the output file if it already
            exists. If ``False`` and the output exists, raise
            :class:`FileExistsError`. Defaults to ``False``.

    Returns:
        The absolute path to the newly created compressed video file. The
        extension is ``.mkv`` for :attr:`CompressionLevel.TRULY_LOSSLESS`
        (Matroska handles lossless HEVC more reliably) and ``.mp4``
        otherwise.

    Raises:
        FileNotFoundError: If ``input_path`` does not exist or is not a file.
        FileExistsError: If the output file already exists and ``overwrite``
            is ``False``.
        subprocess.CalledProcessError: If the ffmpeg process fails.
        RuntimeError: If the ``ffmpeg`` executable is not found on PATH.
    """
    input_path = Path(input_path).expanduser().resolve()

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    is_truly_lossless: bool = compression_level is CompressionLevel.TRULY_LOSSLESS
    # Matroska (.mkv) is a more permissive container for lossless HEVC;
    # some players/muxers reject lossless HEVC inside .mp4.
    output_ext: str = ".mkv" if is_truly_lossless else ".mp4"

    output_dir: Path = input_path.parent / "compressed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path: Path = output_dir / f"{input_path.stem}_compressed{output_ext}"

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}. Pass overwrite=True to replace it.")

    # Assemble video/audio codec arguments based on the chosen level.
    video_args: list[str]
    audio_args: list[str]
    if is_truly_lossless:
        video_args = ["-c:v", "libx265", "-x265-params", "lossless=1"]
        audio_args = ["-c:a", "copy"]  # don't degrade audio in a lossless encode
    else:
        crf: int = int(compression_level.value)
        video_args = ["-c:v", "libx265", "-crf", str(crf)]
        audio_args = ["-c:a", "aac", "-b:a", audio_bitrate]

    cmd: list[str] = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-i",
        str(input_path),
        *video_args,
        "-preset",
        preset,
        *audio_args,
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg executable not found. Install it and ensure it is on PATH.") from exc

    return output_path


if __name__ == "__main__":
    # --- edit these two lines to run ---
    INPUT_VIDEO: Path = Path("/Users/ibadrather/Documents/tral traditional.mp4")
    LEVEL: CompressionLevel = CompressionLevel.VISUALLY_LOSSLESS
    # Options: TRULY_LOSSLESS | VISUALLY_LOSSLESS | HIGH_QUALITY | MODERATE
    # -----------------------------------

    result_path: Path = compress_video(
        input_path=INPUT_VIDEO,
        compression_level=LEVEL,
    )
    print(f"Compressed file written to: {result_path}")
