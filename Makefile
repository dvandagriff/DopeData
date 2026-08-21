.PHONY: demo test live clean format lint

demo:
	python scripts/run_demo.py

test:
	python -m pytest tests/ -v

live:
	python scripts/run_demo.py --mode live --backend pure

clean:
	rm -rf data/snapshots/*.html data/snapshots/freshness_report.csv __pycache__ src/dope/__pycache__ src/dope/*/__pycache__ src/dope/*/*/__pycache__ tests/__pycache__ .pytest_cache

format:
	ruff format src/ scripts/ tests/

lint:
	ruff check src/ scripts/ tests/
	mypy src/dope/
