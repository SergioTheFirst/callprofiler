# -*- coding: utf-8 -*-
"""
torch_patch.py — общий хелпер: torch 2.6 сменил дефолт ``weights_only=True``
у ``torch.load``, чужие чекпоинты (GigaAM/pyannote) не проходят allowlist и
падают. Раньше это патчилось глобально в ``callprofiler/__init__.py`` —
цена: любой ``import callprofiler.*`` тянул torch (даже ``--help``/``doctor``).

Теперь патч применяется ТОЛЬКО на время фактической загрузки чекпоинта —
используй как context manager вокруг ``*.from_pretrained(...)``.
"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def patch_weights_only_false():
    """На время блока: ``torch.load(...)`` получает ``weights_only=False``."""
    import torch

    orig_load = torch.load

    def _patched(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return orig_load(*args, **kwargs)

    torch.load = _patched
    try:
        yield
    finally:
        torch.load = orig_load
