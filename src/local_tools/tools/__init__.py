"""One subpackage per tool.

Each tool package exposes its logic in ``core`` (no Streamlit imports) and its
user interface in ``page`` as a ``render()`` function, so the logic stays
usable from a script or a test.
"""
