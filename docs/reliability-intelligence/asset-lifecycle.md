# Asset Lifecycle

Lifecycle boundaries determine valid observation windows. Installation, standby, planned
shutdown, repair, rebuild, replacement, component replacement, and retirement must remain
explicit. Active assets at the window end are right-censored; history beginning after installation
is left-truncated. Unknown history is never treated as zero age. The normalized lifecycle summary
is fingerprinted for reproducibility.
