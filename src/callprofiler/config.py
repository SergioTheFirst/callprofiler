# -*- coding: utf-8 -*-
"""
config.py — загрузка и валидация конфигурации из YAML.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ModelsConfig:
    whisper: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"
    whisper_beam_size: int = 5
    whisper_language: str = "ru"
    llm_model: str = "qwen2.5:14b-instruct-q4_K_M"
    ollama_url: str = "http://localhost:11434"


@dataclass
class PipelineConfig:
    watch_interval_sec: int = 30
    file_settle_sec: int = 5
    max_retries: int = 3
    retry_interval_sec: int = 3600


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"


@dataclass
class Config:
    data_dir: str = ""
    log_file: str = ""
    hf_token: str = ""
    models: ModelsConfig = field(default_factory=ModelsConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)


def load_config(path: str) -> Config:
    """Загрузить конфиг из YAML-файла, вернуть Config."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg = Config(
        data_dir=raw.get("data_dir", ""),
        log_file=raw.get("log_file", ""),
        hf_token=raw.get("hf_token", ""),
    )

    if "models" in raw:
        m = raw["models"]
        cfg.models = ModelsConfig(
            whisper=m.get("whisper", cfg.models.whisper),
            whisper_device=m.get("whisper_device", cfg.models.whisper_device),
            whisper_compute=m.get("whisper_compute", cfg.models.whisper_compute),
            whisper_beam_size=m.get("whisper_beam_size", cfg.models.whisper_beam_size),
            whisper_language=m.get("whisper_language", cfg.models.whisper_language),
            llm_model=m.get("llm_model", cfg.models.llm_model),
            ollama_url=m.get("ollama_url", cfg.models.ollama_url),
        )

    if "pipeline" in raw:
        p = raw["pipeline"]
        cfg.pipeline = PipelineConfig(
            watch_interval_sec=p.get("watch_interval_sec", cfg.pipeline.watch_interval_sec),
            file_settle_sec=p.get("file_settle_sec", cfg.pipeline.file_settle_sec),
            max_retries=p.get("max_retries", cfg.pipeline.max_retries),
            retry_interval_sec=p.get("retry_interval_sec", cfg.pipeline.retry_interval_sec),
        )

    if "audio" in raw:
        a = raw["audio"]
        cfg.audio = AudioConfig(
            sample_rate=a.get("sample_rate", cfg.audio.sample_rate),
            channels=a.get("channels", cfg.audio.channels),
            format=a.get("format", cfg.audio.format),
        )

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    """Проверить наличие data_dir и доступность ffmpeg."""
    if cfg.data_dir and not Path(cfg.data_dir).exists():
        raise FileNotFoundError(f"data_dir не существует: {cfg.data_dir}")

    if not shutil.which("ffmpeg"):
        raise EnvironmentError("ffmpeg не найден в PATH")
