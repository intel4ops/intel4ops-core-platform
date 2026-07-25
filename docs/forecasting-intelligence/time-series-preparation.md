# Time-series preparation

Inputs are ordered chronologically and fingerprinted with their governed policies. Duplicate
periods are blocked. Partial periods default to exclusion. Missing periods default to blocking;
zero fill, forward fill, historical-median fill, and bounded linear interpolation are explicit
alternatives with an imputation limit and trace. Confirmed data errors may be excluded only
under the matching policy. Raw values are not copied into audit steps.
