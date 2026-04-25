# -*- coding: utf-8 -*-
"""Graph module constants — thresholds, decay coefficients, algorithm names."""

# Anti-noise filters applied in builder.py before writing facts to DB.
MIN_FACT_CONFIDENCE: float = 0.6
MIN_QUOTE_LENGTH: int = 5

# Time-decay half-life for relation weights (in days).
# A relation not seen for RELATION_DECAY_DAYS contributes half its original weight.
RELATION_DECAY_DAYS: int = 180

# Algorithm used to compute fact_id deduplication hashes.
FACT_ID_ALGORITHM: str = "sha256"
FACT_ID_LENGTH: int = 16  # truncated hex chars (64 bits — sufficient for dedup)

# BS-index formula version tag stored in entity_metrics.
# v1_linear: weighted linear combination (current).
# When calibrated with real data, bump to v2_logistic and update aggregator.py.
BS_FORMULA_VERSION: str = "v1_linear"
