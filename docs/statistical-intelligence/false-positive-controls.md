# False-Positive Controls

OIKB parameters and tenant suppression records govern minimum sample, history and
peer counts; persistence and recurrence; cooldown-compatible effective windows;
known-event, planned-maintenance and approved-business-event exclusions; minimum
confidence, deviation and materiality; and explicit suppression.

The engine does not embed customer thresholds. Suppressed observations retain their
method, baseline and component trace but are not marked as active anomalies. Review
feedback records whether an assessment was actionable or a false positive without
altering immutable execution evidence.
