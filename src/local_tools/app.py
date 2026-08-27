"""Streamlit entry point: serves every tool from one app.

Run it with::

    make app          # or: uv run streamlit run src/local_tools/app.py

``.streamlit/config.toml`` binds the server to every interface, so the app is
reachable from other machines on the same network at ``http://<host>:8501``.
Because the server does the work, every path a tool shows or accepts belongs
to the machine running this app, not to the visitor's computer.

To add a tool:

1. Create ``local_tools/tools/<name>/`` with a ``core`` module holding the
   logic (no Streamlit imports) and a ``page`` module exposing ``render()``.
2. Append one :func:`streamlit.Page` to :data:`PAGES` below.
"""

from __future__ import annotations

import streamlit as st

from local_tools.tools.video_compression.page import render as render_video_compression

#: Every tool, in the order they appear in the sidebar. The first is the landing page.
PAGES: list[st.Page] = [
    st.Page(
        render_video_compression,
        title="Video compression",
        icon=":material/movie:",
        url_path="video-compression",
        default=True,
    ),
]


def main() -> None:
    """Configure the app and run whichever page is selected."""
    st.set_page_config(
        page_title="Local tools",
        page_icon=":material/handyman:",
        layout="centered",
    )
    st.navigation(PAGES).run()


if __name__ == "__main__":
    main()
