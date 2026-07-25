# OIKB Formula Schema

Expressions are bounded JSON objects. They contain an operation, named input references,
bounded filters and grouping metadata, and named parameters. They never contain Python,
JavaScript, SQL, functions, executable source, or dynamically loaded code.

The schema recognizes the OIKB operation vocabulary, but WP-2.10 exports only operations
already implemented by WP-2.07: count, distinct count, sum, average, minimum, maximum,
ratio, percentage, absolute variance, percentage variance, and reconciliation.
Recognized but unimplemented operations return an explicit unsupported error.

Each version also declares output type and unit, optional ISO currency, null and
zero-denominator policies, deterministic rounding, Trust requirements, readiness
requirements, input contracts, parameters, and evidence contracts.

Input references must be declared. Compatible arithmetic inputs must use one unit and
match the output unit. Currency inputs must use one explicit currency matching the
output. No FX or unit conversion occurs implicitly. Percentage outputs are explicitly
labelled `percent`; decimal ratios remain distinct.

The version fingerprint is SHA-256 over canonical sorted JSON containing the complete
execution contract. Reordering JSON keys does not change the fingerprint.
