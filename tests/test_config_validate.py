# -*- coding: utf-8 -*-
"""test_config_validate.py — T-01: config preflight (empty/broken YAML, semantic contract)."""
from __future__ import annotations

import pytest
import yaml

from callprofiler.config import Config, load_config, validate_config


def _write(tmp_path, name, content: str):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _valid_cfg(tmp_path) -> Config:
    """A Config that passes validate_config cleanly."""
    return Config(
        data_dir=str(tmp_path),
    )


# ── empty / broken YAML → clear error, not AttributeError ──────────────────


def test_empty_yaml_file_raises_clear_error(tmp_path):
    p = _write(tmp_path, "empty.yaml", "")
    with pytest.raises(ValueError, match="data_dir"):
        load_config(str(p))


def test_yaml_with_only_comment_raises_clear_error(tmp_path):
    p = _write(tmp_path, "commentonly.yaml", "# just a comment\n")
    with pytest.raises(ValueError, match="data_dir"):
        load_config(str(p))


def test_valid_minimal_yaml_loads(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    p = _write(
        tmp_path,
        "ok.yaml",
        yaml.safe_dump({
            "data_dir": str(data_dir),
            "models": {"asr_backend": "whisper"},
        }),
    )
    import shutil
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH on this dev box")
    cfg = load_config(str(p))
    assert cfg.data_dir == str(data_dir)


# ── validate_config: semantic contract (pure function, no I/O side effects) ─


def test_valid_config_has_no_errors(tmp_path):
    errors, warnings = validate_config(_valid_cfg(tmp_path))
    assert errors == []


def test_missing_data_dir_is_error():
    cfg = Config(data_dir="")
    errors, _ = validate_config(cfg)
    assert any("data_dir" in e for e in errors)


def test_non_loopback_llm_url_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.models.llm_url = "http://evil.example.com/v1/chat/completions"
    errors, _ = validate_config(cfg)
    assert any("loopback" in e for e in errors)


def test_loopback_llm_url_ok(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.models.llm_url = "http://localhost:8080/v1/chat/completions"
    errors, _ = validate_config(cfg)
    assert errors == []


def test_negative_max_retries_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.pipeline.max_retries = -1
    errors, _ = validate_config(cfg)
    assert any("max_retries" in e for e in errors)


def test_zero_watch_interval_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.pipeline.watch_interval_sec = 0
    errors, _ = validate_config(cfg)
    assert any("watch_interval_sec" in e for e in errors)


def test_unknown_asr_backend_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.models.asr_backend = "whispercpp"
    errors, _ = validate_config(cfg)
    assert any("asr_backend" in e for e in errors)


def test_gigaam_backend_without_model_dir_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.models.asr_backend = "gigaam"
    cfg.models.gigaam_model_dir = ""
    errors, _ = validate_config(cfg)
    assert any("gigaam_model_dir" in e for e in errors)


def test_gigaam_backend_with_model_dir_ok(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.models.asr_backend = "gigaam"
    cfg.models.gigaam_model_dir = str(tmp_path)  # existence not required here
    errors, _ = validate_config(cfg)
    assert errors == []


def test_data_dir_and_text_export_dir_collision_is_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.pipeline.text_export_dir = str(tmp_path)
    errors, _ = validate_config(cfg)
    assert any("пересекаются" in e for e in errors)


def test_diarization_without_hf_token_is_warning_not_error(tmp_path):
    cfg = _valid_cfg(tmp_path)
    cfg.features.enable_diarization = True
    cfg.hf_token = ""
    errors, warnings = validate_config(cfg)
    assert errors == []
    assert any("hf_token" in w for w in warnings)
