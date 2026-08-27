.PHONY: app lint

app:
	uv run streamlit run src/local_tools/app.py

lint:
	uv run ruff format src/
	uv run ruff check src/
