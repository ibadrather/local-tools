"""Video compression: an ffmpeg/libx265 wrapper plus its Streamlit page."""

from local_tools.tools.video_compression.core import (
    PRESETS,
    CompressionError,
    CompressionLevel,
    compress_video,
    default_output_path,
)

__all__ = [
    "PRESETS",
    "CompressionError",
    "CompressionLevel",
    "compress_video",
    "default_output_path",
]
