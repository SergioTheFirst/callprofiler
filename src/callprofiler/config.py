# -*- coding: utf-8 -*-
"""
config.py — загрузка и валидация конфигурации из YAML.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _resolve_secret(raw: str) -> str:
    """Резолв секрета из окружения (``${VAR}`` / ``%VAR%``) → значение или "".

    Баг, который чинит эта функция: на Windows ``os.path.expandvars('${HF_TOKEN}')``
    при НЕзаданной переменной возвращает строку ``'${HF_TOKEN}'`` (truthy!), а не
    "". Этот мусор уходил в pyannote как ``use_auth_token`` → 401 на gated-моделях
    → диаризация молча падала → все роли UNKNOWN. Незаданная переменная ОБЯЗАНА
    давать "" — чтобы вызывающий код мог честно проверить "токен не задан".
    """
    if not raw:
        return ""
    val = os.path.expandvars(raw).strip()
    # expandvars оставляет незаданные ${VAR}/%VAR% дословно — считаем "не задано".
    if val.startswith("${") and val.endswith("}"):
        return ""
    if val.startswith("%") and val.endswith("%"):
        return ""
    return val


@dataclass
class ModelsConfig:
    whisper: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"
    whisper_beam_size: int = 5
    whisper_language: str = "ru"
    llm_model: str = "local"
    llm_url: str = "http://127.0.0.1:8080/v1/chat/completions"
    # Окно контекста llama-server на старте (флаг ``-c``). Master-ручка
    # динамического бюджета вывода: per-call max_tokens = n_ctx - prompt - запас.
    # Определяется VRAM на боксе (12GB → 16384 на Q8_0 безопасно). См.
    # DYNAMIC_TOKEN_BUDGET_PLAN.md и analyze/output_budget.py.
    llm_n_ctx: int = 16384
    asr_backend: str = "whisper"  # "whisper" | "gigaam"
    gigaam_url: str = ""          # legacy HTTP endpoint (не используется локальной моделью)
    gigaam_model_dir: str = ""    # каталог локальной GigaAM (HF, trust_remote_code)
    gigaam_device: str = "cuda"   # "cuda" | "cpu"
    gigaam_chunk_sec: float = 20.0    # длина окна нарезки (<25с, ограничение модели)
    gigaam_overlap_sec: float = 0.0   # перекрытие окон (0 = без дублей на стыках)
    pyannote_batch_size: int = 32     # батч инференса диаризации (1=серийно/медленно)


@dataclass
class PipelineConfig:
    watch_interval_sec: int = 30
    file_settle_sec: int = 5
    max_retries: int = 3
    retry_interval_sec: int = 3600
    text_export_dir: str = ""             # куда писать читабельный .txt транскрипт ("" = не писать)
    remove_source_on_success: bool = True  # удалять исходник из incoming после транскрибации
    batch_chunk_size: int = 100            # размер партии в process_pending (RAM/resume на больших прогонах)
    delete_normalized_after_transcribe: bool = False  # удалять normalized .wav после stage 2 (экономия диска)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"


@dataclass
class FeaturesConfig:
    """Feature-флаги pipeline-этапов. См. configs/features.yaml."""
    enable_diarization: bool = True
    enable_llm_analysis: bool = True
    enable_profanity_detection: bool = True
    enable_name_extraction: bool = True
    enable_event_extraction: bool = True
    enable_telegram_notification: bool = False
    enable_graph_update: bool = True


@dataclass
class Config:
    data_dir: str = ""
    log_file: str = ""
    hf_token: str = ""
    # prompts резолвятся от КОРНЯ ПРОЕКТА (а не от data_dir) — иначе ломается,
    # когда data_dir вне дерева проекта (напр. C:\calls\data). Override через YAML.
    prompts_dir: str = field(
        default_factory=lambda: str(
            Path(__file__).resolve().parents[2] / "configs" / "prompts"
        )
    )
    models: ModelsConfig = field(default_factory=ModelsConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)


def load_config(path: str) -> Config:
    """Загрузить конфиг из YAML-файла, вернуть Config.

    Дополнительно ищет features.yaml рядом с основным конфигом и
    объединяет (отсутствие файла → дефолты FeaturesConfig).
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg = Config(
        data_dir=raw.get("data_dir", ""),
        log_file=raw.get("log_file", ""),
        hf_token=_resolve_secret(raw.get("hf_token", "")),
    )

    # prompts_dir: YAML override, иначе дефолт (корень проекта/configs/prompts)
    if raw.get("prompts_dir"):
        cfg.prompts_dir = raw["prompts_dir"]

    if "models" in raw:
        m = raw["models"]
        cfg.models = ModelsConfig(
            whisper=m.get("whisper", cfg.models.whisper),
            whisper_device=m.get("whisper_device", cfg.models.whisper_device),
            whisper_compute=m.get("whisper_compute", cfg.models.whisper_compute),
            whisper_beam_size=m.get("whisper_beam_size", cfg.models.whisper_beam_size),
            whisper_language=m.get("whisper_language", cfg.models.whisper_language),
            llm_model=m.get("llm_model", cfg.models.llm_model),
            llm_url=m.get("llm_url", cfg.models.llm_url),
            llm_n_ctx=int(m.get("llm_n_ctx", cfg.models.llm_n_ctx)),
            asr_backend=m.get("asr_backend", cfg.models.asr_backend),
            gigaam_url=m.get("gigaam_url", cfg.models.gigaam_url),
            gigaam_model_dir=m.get("gigaam_model_dir", cfg.models.gigaam_model_dir),
            gigaam_device=m.get("gigaam_device", cfg.models.gigaam_device),
            gigaam_chunk_sec=float(m.get("gigaam_chunk_sec", cfg.models.gigaam_chunk_sec)),
            gigaam_overlap_sec=float(m.get("gigaam_overlap_sec", cfg.models.gigaam_overlap_sec)),
            pyannote_batch_size=int(m.get("pyannote_batch_size", cfg.models.pyannote_batch_size)),
        )

    if "pipeline" in raw:
        p = raw["pipeline"]
        cfg.pipeline = PipelineConfig(
            watch_interval_sec=p.get("watch_interval_sec", cfg.pipeline.watch_interval_sec),
            file_settle_sec=p.get("file_settle_sec", cfg.pipeline.file_settle_sec),
            max_retries=p.get("max_retries", cfg.pipeline.max_retries),
            retry_interval_sec=p.get("retry_interval_sec", cfg.pipeline.retry_interval_sec),
            text_export_dir=p.get("text_export_dir", cfg.pipeline.text_export_dir),
            remove_source_on_success=bool(
                p.get("remove_source_on_success", cfg.pipeline.remove_source_on_success)
            ),
        )

    if "audio" in raw:
        a = raw["audio"]
        cfg.audio = AudioConfig(
            sample_rate=a.get("sample_rate", cfg.audio.sample_rate),
            channels=a.get("channels", cfg.audio.channels),
            format=a.get("format", cfg.audio.format),
        )

    cfg.features = _load_features(Path(path).parent, raw.get("features"))

    _validate(cfg)
    return cfg


def _load_features(config_dir: Path, inline: dict | None) -> FeaturesConfig:
    """Загрузить FeaturesConfig.

    Приоритет: inline-секция в base.yaml > features.yaml рядом с base.yaml > defaults.
    """
    feats = FeaturesConfig()
    raw: dict | None = inline

    if raw is None:
        feat_path = config_dir / "features.yaml"
        if feat_path.exists():
            with open(feat_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

    if not raw:
        return feats

    return FeaturesConfig(
        enable_diarization=bool(raw.get("enable_diarization", feats.enable_diarization)),
        enable_llm_analysis=bool(raw.get("enable_llm_analysis", feats.enable_llm_analysis)),
        enable_profanity_detection=bool(
            raw.get("enable_profanity_detection", feats.enable_profanity_detection)
        ),
        enable_name_extraction=bool(
            raw.get("enable_name_extraction", feats.enable_name_extraction)
        ),
        enable_event_extraction=bool(
            raw.get("enable_event_extraction", feats.enable_event_extraction)
        ),
        enable_telegram_notification=bool(
            raw.get("enable_telegram_notification", feats.enable_telegram_notification)
        ),
        enable_graph_update=bool(
            raw.get("enable_graph_update", feats.enable_graph_update)
        ),
    )


def _validate(cfg: Config) -> None:
    """Проверить наличие data_dir и доступность ffmpeg."""
    if cfg.data_dir and not Path(cfg.data_dir).exists():
        raise FileNotFoundError(f"data_dir не существует: {cfg.data_dir}")

    if not shutil.which("ffmpeg"):
        raise EnvironmentError("ffmpeg не найден в PATH")
