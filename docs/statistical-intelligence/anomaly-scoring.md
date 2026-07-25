# Anomaly Scoring

Scores use a documented 0.00–1.00 scale. `statistical_score` combines bounded
deviation, confidence, materiality, persistence, recurrence, and Trust contribution.
Every contribution is stored separately with raw value, normalized value, weight,
contribution, and explanation.

`confidence_score` describes statistical support, not certainty.
`materiality_score` describes business importance. Severity combines both and is not
derived from extremeness alone. An anomaly means a material governed deviation from a
baseline; it is not proof of fraud, failure, theft, waste, misconduct, or causation.
