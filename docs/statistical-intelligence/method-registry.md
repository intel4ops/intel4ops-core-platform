# Statistical Method Registry

Every executable method has a stable code, version, capability class, minimum sample
size, feature flags, bounded parameter contract, output contract, and implementation
reference. Duplicate code/version registration fails and unregistered methods return
`UNSUPPORTED`.

Version 1.0 supports descriptive statistics; Z-score, modified Z-score, IQR,
percentile and standard-deviation outliers; median, trimmed and winsorized baselines;
rolling median/MAD; peer Z-score, robust Z-score, percentile and ratio deviation;
rolling Z-score, robust Z-score and IQR; EWMA; CUSUM-style bounded change detection;
linear trend, slope change and level shift; and weighted, maximum and robust normalized
composite scores. All calculations reject non-finite values and bounded parameters are
validated before use.
