.PHONY: app lint

# Serves on every interface (see .streamlit/config.toml); run from the repo root.
app:
	uv run streamlit run src/local_tools/app.py

lint:
	uv run ruff format src/
	uv run ruff check src/
