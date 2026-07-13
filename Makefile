# HELIOS CFO Digital Twin — build & run orchestration
# All targets assume you run from repo root. PYTHONPATH=. exposes the src package.

PY=PYTHONPATH=. python

.PHONY: help install warehouse kpis variance forecast scenarios assistant reports api app all clean

help:
	@echo "Targets:"
	@echo "  install    pip install -r requirements.txt"
	@echo "  warehouse  generate data + build SQLite star schema + gold parquet"
	@echo "  kpis       print the tech-finance KPI suite"
	@echo "  variance   print revenue/comp/P&L variance bridges"
	@echo "  forecast   run the ensemble forecast + walk-forward backtest"
	@echo "  scenarios  compare all 6 what-if scenarios vs Base Plan"
	@echo "  assistant  demo the conversational CFO assistant"
	@echo "  reports    write QBR / Board / Earnings markdown to reports/"
	@echo "  api        launch FastAPI on :8000"
	@echo "  app        launch Streamlit dashboards on :8501"
	@echo "  all        warehouse -> reports (full offline pipeline)"

install:
	pip install -r requirements.txt --break-system-packages

warehouse:
	$(PY) -m src.warehouse.build_warehouse

kpis:
	$(PY) -m src.analytics.kpis

variance:
	$(PY) -m src.analytics.variance

forecast:
	$(PY) -m src.forecasting.pipeline

scenarios:
	$(PY) -m src.scenarios.compare

assistant:
	$(PY) -m src.narration.cfo_assistant

reports:
	$(PY) -m src.narration.reports

api:
	$(PY) -m uvicorn api.main:app --reload --port 8000

app:
	$(PY) -m streamlit run app/streamlit_app.py

all: warehouse reports
	@echo "Offline pipeline complete. Run 'make app' or 'make api' to serve."

clean:
	rm -f data/helios.db data/gold_monthly.parquet data/raw/*.csv
	rm -f reports/*.md
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
