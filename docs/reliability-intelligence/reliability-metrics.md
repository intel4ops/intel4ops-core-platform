# Reliability Metrics

Basic metrics preserve numerator and denominator:

- failure rate = failures / exposure;
- repair rate = repairs / repair time;
- MTBF = operating exposure excluding downtime / failures;
- MTTF = exposure / failures;
- MTTR = repair duration / repairs;
- operational availability = (exposure - downtime) / exposure;
- unplanned downtime ratio = downtime / exposure.

Zero exposure yields a non-estimable result. Zero failures are reported but never interpreted as
zero future risk. Negative and non-finite values are rejected.
