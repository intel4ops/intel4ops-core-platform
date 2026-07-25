# Error metrics

Supported metrics are MAE, median absolute error, RMSE, MAPE, SMAPE, WAPE, MASE, mean error,
bias percentage, interval coverage, and interval width. MAPE is null when any actual is zero or
near zero. WAPE, MASE, and bias denominators are validated. Undefined results are persisted as
structured nulls with an invalid reason; NaN and infinity are never persisted.
