"""
Forecasting pipeline.

Three model families, then a backtested ensemble:

  1. ARIMA (statsmodels)        -- classical statistical baseline
  2. Prophet (optional)         -- handles the strong Q4 seasonality we baked in
  3. XGBoost on engineered      -- learns driver relationships (lags, marketing,
     features                      season, macro) rather than the raw series
  4. Ensemble                   -- weights chosen by walk-forward backtest (inverse
                                   WAPE), the way you'd actually justify weights

Key FP&A point baked into the design: for planning we don't only forecast the
top-line series. The XGBoost model forecasts *drivers* (e.g. new logos, ARPU) and
the integrated model turns drivers into financials. This is the difference between
statistical forecasting and FP&A forecasting; the ensemble reconciles the two.

Every model is wrapped so a missing optional dependency (Prophet/XGBoost) is skipped
rather than crashing the pipeline.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]


def wape(actual, pred):
    actual, pred = np.asarray(actual), np.asarray(pred)
    return np.abs(actual - pred).sum() / np.abs(actual).sum()


# --------------------------------------------------------------------------- #
# Individual model wrappers (each: fit on history, return h-step forecast)
# --------------------------------------------------------------------------- #
def forecast_arima(y: pd.Series, h: int) -> np.ndarray | None:
    try:
        from statsmodels.tsa.arima.model import ARIMA
        m = ARIMA(y.values, order=(2, 1, 2)).fit()
        return m.forecast(h)
    except Exception:
        return None


def forecast_prophet(y: pd.Series, dates: pd.Series, h: int) -> np.ndarray | None:
    try:
        from prophet import Prophet
        dfp = pd.DataFrame({"ds": pd.to_datetime(dates), "y": y.values})
        m = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                    daily_seasonality=False)
        m.fit(dfp)
        future = m.make_future_dataframe(periods=h, freq="MS")
        return m.predict(future)["yhat"].values[-h:]
    except Exception:
        return None


def forecast_xgboost(df: pd.DataFrame, target: str, h: int,
                     feature_cols: list[str]) -> np.ndarray | None:
    """Lag + driver features. Recursive multi-step forecast."""
    try:
        from xgboost import XGBRegressor
    except Exception:
        return None
    d = df.copy().reset_index(drop=True)
    for lag in (1, 2, 3, 12):
        d[f"{target}_lag{lag}"] = d[target].shift(lag)
    d["month"] = pd.to_datetime(d["date"]).dt.month
    feats = feature_cols + [f"{target}_lag{l}" for l in (1, 2, 3, 12)] + ["month"]
    train = d.dropna(subset=feats + [target])
    if len(train) < 18:
        return None
    model = XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                         subsample=0.9, colsample_bytree=0.9, random_state=42)
    model.fit(train[feats], train[target])
    # recursive forecast
    hist = d.copy()
    preds = []
    last_date = pd.to_datetime(hist["date"]).max()
    for step in range(h):
        nd = last_date + pd.DateOffset(months=step + 1)
        row = {c: hist[c].iloc[-1] for c in feature_cols}     # hold drivers flat
        for lag in (1, 2, 3, 12):
            row[f"{target}_lag{lag}"] = (preds[-lag] if lag <= len(preds)
                                         else hist[target].iloc[-(lag - len(preds))])
        row["month"] = nd.month
        yhat = float(model.predict(pd.DataFrame([row])[feats])[0])
        preds.append(yhat)
    return np.array(preds)


# --------------------------------------------------------------------------- #
# Ensemble with walk-forward backtest
# --------------------------------------------------------------------------- #
def ensemble_forecast(df: pd.DataFrame, target: str = "revenue", h: int = 6,
                      feature_cols: list[str] | None = None) -> dict:
    feature_cols = feature_cols or ["marketing_spend", "total_mau_m", "cloud_customers"]
    y = df[target].reset_index(drop=True)
    dates = df["date"].reset_index(drop=True)

    # --- backtest: hold out last `h`, score each model by WAPE ---
    cut = len(y) - h
    y_tr, y_te = y.iloc[:cut], y.iloc[cut:]
    members, scores, bt = {}, {}, {}
    cand = {
        "arima": forecast_arima(y_tr, h),
        "prophet": forecast_prophet(y_tr, dates.iloc[:cut], h),
        "xgboost": forecast_xgboost(df.iloc[:cut], target, h, feature_cols),
    }
    for name, fc in cand.items():
        if fc is not None and len(fc) == h:
            bt[name] = fc
            scores[name] = wape(y_te.values, fc)

    if not scores:
        raise RuntimeError("No forecasting models available")

    # inverse-WAPE weights (better backtest -> more weight)
    inv = {k: 1.0 / (v + 1e-6) for k, v in scores.items()}
    tot = sum(inv.values())
    weights = {k: inv[k] / tot for k in inv}

    # --- refit on full history for the live forecast ---
    full = {
        "arima": forecast_arima(y, h),
        "prophet": forecast_prophet(y, dates, h),
        "xgboost": forecast_xgboost(df, target, h, feature_cols),
    }
    avail = {k: v for k, v in full.items() if v is not None and k in weights}
    ens = sum(weights[k] * np.asarray(avail[k]) for k in avail)
    # renormalize if a model dropped out at full-fit time
    wsum = sum(weights[k] for k in avail)
    ens = ens / wsum if wsum else ens

    future_dates = [pd.to_datetime(dates).max() + pd.DateOffset(months=i + 1)
                    for i in range(h)]

    # --- confidence bands ---
    # Empirical: scale backtest residual spread by horizon (uncertainty grows sqrt(t)),
    # widened by member disagreement so the band is honest when models diverge.
    best = min(scores, key=scores.get)
    resid_sd = float(np.std(y_te.values - np.asarray(bt[best])))
    member_matrix = np.vstack([np.asarray(v) for v in avail.values()])
    disagreement = member_matrix.std(axis=0) if len(avail) > 1 else np.zeros(h)
    step = np.sqrt(np.arange(1, h + 1))
    band = 1.28 * (resid_sd * step + disagreement)          # ~80% interval
    band_95 = 1.96 * (resid_sd * step + disagreement)       # ~95% interval
    ens_arr = np.asarray(ens)

    return {
        "target": target, "horizon": h,
        "future_dates": [d.strftime("%Y-%m") for d in future_dates],
        "ensemble": ens_arr.tolist(),
        "lower_80": (ens_arr - band).tolist(),
        "upper_80": (ens_arr + band).tolist(),
        "lower_95": (ens_arr - band_95).tolist(),
        "upper_95": (ens_arr + band_95).tolist(),
        "members": {k: np.asarray(v).tolist() for k, v in avail.items()},
        "weights": weights,
        "backtest_wape": scores,
    }


if __name__ == "__main__":
    df = pd.read_parquet(ROOT / "data" / "gold_monthly.parquet")
    hist = df[df["scenario"] == "Reported actuals"].sort_values("date").reset_index(drop=True)
    res = ensemble_forecast(hist, "revenue", h=6)
    print("Backtest WAPE:", {k: round(v, 4) for k, v in res["backtest_wape"].items()})
    print("Ensemble weights:", {k: round(v, 3) for k, v in res["weights"].items()})
    print("Next 6 months revenue ($B):",
          [round(x / 1e9, 2) for x in res["ensemble"]])
