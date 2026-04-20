# -*- coding: utf-8 -*-
"""
biography — multi-pass LLM pipeline turning a corpus of call transcripts
into a coherent biographical book.

Pipeline (10 passes, all DB-backed, resumable):

    P1.  Scene Extractor    — per-call narrative unit (synopsis, tone, entities)
    P2.  Entity Resolver    — canonicalize Vasya/Вася/Василий Петрович
    P3.  Thread Builder     — temporal thread per entity (chronological scenes)
    P4.  Arc Detector       — multi-call arcs (problem → investigation → outcome)
    P5.  Portrait Writer    — character sketches for recurring entities
    P6.  Chapter Writer     — monthly / thematic prose chapters
    P8.  Editorial Pass     — polish, tighten, save status='final' per chapter
    P8b. Doc Dedup          — cross-chapter paragraph dedup (deterministic, no LLM)
    P7.  Book Assembler     — TOC + prologue + final chapters + epilogue
    P9.  Yearly Summary     — Dovlatov-style annual retrospective

Every LLM call is memoized in bio_llm_calls (hash-keyed), so re-running
a pass skips prompts that were already answered. Designed to run for days.
"""
