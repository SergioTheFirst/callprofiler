# -*- coding: utf-8 -*-
"""Knowledge Graph layer for CallProfiler.

3-layer separation:
  Extraction   — LLM outputs entities/relations/structured_facts in v2 analyses
  Aggregation  — Python (deterministic): GraphBuilder + EntityMetricsAggregator
  Interpretation — LLM receives structured aggregates (metrics + facts), not raw transcripts

Only analyses with schema_version='v2' are processed by this module.
"""

from callprofiler.graph.builder import GraphBuilder
from callprofiler.graph.aggregator import EntityMetricsAggregator

__all__ = ["GraphBuilder", "EntityMetricsAggregator"]
