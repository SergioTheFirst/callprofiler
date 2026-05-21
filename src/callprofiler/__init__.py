import torch as _torch

_original_load = _torch.load


def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_load(*args, **kwargs)


_torch.load = _patched_load
