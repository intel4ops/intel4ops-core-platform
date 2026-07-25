# Statistical Intelligence Architecture

WP-2.11 adds an explainable statistical layer between governed OIKB knowledge and
WP-2.08 finding publication. Trust remains the data-quality authority, analytical
readiness remains the eligibility authority, OIKB remains the knowledge authority,
and the statistical engine is only the execution authority for explicitly registered
methods.

The flow is: tenant authorization, active OIKB resolution, immutable execution-package
export, Trust and explicit statistical-readiness checks, bounded method resolution,
aggregate baseline creation, method execution, explainable scoring, false-positive
controls, evidence-ready output, and optional WP-2.09 orchestration. Raw canonical
records are accepted only as bounded request inputs and are not persisted.

The engine uses the simplest governed method. It contains no expression evaluator,
dynamic import, submitted code, unrestricted SQL, model training, or causal inference.
