# Model selection

OIKB supplies candidates and the primary metric. Unsupported, unready, and failed candidates
are rejected before ranking. The naïve candidate remains visible. Eligible candidates are
ranked deterministically by metric, complexity, and code; the simplest method within five
percent of the best score is selected. The ranking and rationale do not claim universal
optimality.
