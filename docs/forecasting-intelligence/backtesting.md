# Backtesting

WP-2.12 supports deterministic holdout and rolling-origin policies. Candidate folds train only
on observations preceding the forecast origin; future observations never enter training or
imputation. Fold records retain train bounds, origin, target period, horizon, point estimate,
actual, errors, and optional interval fields. Insufficient folds produce `BACKTEST_FAILED`.
