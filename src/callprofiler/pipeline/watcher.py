# -*- coding: utf-8 -*-
"""
watcher.py — автоматический мониторинг папок пользователей.

Сканирует incoming_dir каждого пользователя (рекурсивно, с подпапками),
находит новые аудиофайлы, регистрирует их через Ingester, запускает
Orchestrator, а после успешной транскрибации убирает исходники из incoming
(копия уже в архиве users/{uid}/audio/originals/YYYY/MM).

Цикл (run_loop):
  1. scan_all_users()        — найти новые файлы, зарегистрировать в БД
  2. process_batch(new_ids)  — обработать новые звонки
  3. cleanup_sources()       — убрать исходники транскрибированных из incoming
  4. retry_errors()          — повторить ошибочные
  5. _maybe_autofit()        — debounced insight-fit (архетипы) по новым терминальным
  6. sleep(watch_interval_sec)
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository
    from callprofiler.ingest.ingester import Ingester
    from callprofiler.pipeline.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Поддерживаемые аудио-форматы
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac", ".wma"}

# pipeline_stage >= этого значения → транскрипт сохранён (можно убирать исходник)
_TRANSCRIBED_STAGE = 2


class FileWatcher:
    """Мониторинг папок пользователей и запуск обработки новых файлов.

    Использование:
        watcher = FileWatcher(config, repo, ingester, orchestrator)
        new_ids = watcher.scan_all_users()   # однократное сканирование
        watcher.run_loop()                    # бесконечный цикл
    """

    def __init__(
        self,
        config: Config,
        repo: Repository,
        ingester: Ingester,
        orchestrator: Orchestrator,
    ) -> None:
        """Инициализировать FileWatcher.

        Параметры:
            config       — конфигурация проекта
            repo         — Repository для доступа к данным
            ingester     — Ingester для регистрации файлов
            orchestrator — Orchestrator для обработки звонков
        """
        self.config = config
        self.repo = repo
        self.ingester = ingester
        self.orchestrator = orchestrator
        # call_id → (user_id, incoming-корень, исходный путь) за последнее сканирование
        self._last_sources: dict[int, tuple[str, Path, Path]] = {}
        # Авто-fit insight (Ф0 плана досье): per-user счётчик терминальных + debounce
        self._terminal_seen: dict[str, int] = {}
        self._new_terminal_since_fit = 0
        self._last_autofit_ts = 0.0
        logger.info("FileWatcher инициализирован")

    def scan_all_users(self) -> list[int]:
        """Сканировать incoming_dir всех пользователей.

        Заполняет ``self._last_sources`` (call_id → исходный путь) для
        последующей очистки. Возвращает список новых call_id.
        """
        self._last_sources = {}

        users = self.repo.get_all_users()
        if not users:
            logger.debug("Нет зарегистрированных пользователей")
            return []

        new_call_ids: list[int] = []

        for user in users:
            user_id = user["user_id"]
            incoming_dir = user.get("incoming_dir", "")

            if not incoming_dir:
                logger.debug("У пользователя %s не задан incoming_dir", user_id)
                continue

            incoming_path = Path(incoming_dir)
            if not incoming_path.exists():
                logger.warning(
                    "incoming_dir не существует: %s (user_id=%s)",
                    incoming_dir, user_id,
                )
                continue

            new_call_ids.extend(self._scan_user_dir(user_id, incoming_path))

        if new_call_ids:
            logger.info("Найдено %d новых файлов", len(new_call_ids))

        return new_call_ids

    def run_once(self) -> int:
        """Один цикл: scan → обработать pending/stalled → cleanup → retry, выход.

        Для тестового/пакетного прогона (bat). Обрабатывает не только новые файлы,
        но и весь backlog (status new/normalizing) через process_pending — иначе
        при повторном запуске «0 new» оставлял бы незаконченные звонки висеть.
        Возвращает число новых зарегистрированных файлов.
        """
        self._update_terminal_counter()  # baseline ДО обработки → delta = обработанные сейчас
        new_ids = self.scan_all_users()
        # process_pending обрабатывает и только что зарегистрированные, и зависшие
        self.orchestrator.process_pending()
        self.cleanup_sources()
        self.cleanup_normalized()
        self.orchestrator.retry_errors()
        self._update_terminal_counter()
        self._maybe_autofit()
        return len(new_ids)

    def run_loop(self) -> None:
        """Запустить бесконечный цикл мониторинга."""
        interval = self.config.pipeline.watch_interval_sec
        logger.info("Запуск цикла мониторинга (интервал=%d сек)", interval)

        try:
            # baseline: исторические терминальные звонки не триггерят fit на старте
            self._update_terminal_counter()
        except Exception as exc:  # noqa: BLE001 — БД может быть ещё не готова
            logger.debug("Baseline терминальных не снят: %s", exc)

        while True:
            try:
                new_ids = self.scan_all_users()

                if new_ids:
                    self.orchestrator.process_batch(new_ids)

                # Добрать зависшие (status new/normalizing) — краш/сбой могли
                # оставить звонки в промежуточном состоянии с готовым WAV.
                self.orchestrator.process_pending()

                # Убрать исходники успешно транскрибированных
                self.cleanup_sources()
                # Подчистить normalized .wav (стадия>=2/терминальные) — не копятся
                self.cleanup_normalized()

                # Повторить ошибочные
                self.orchestrator.retry_errors()

                # Авто-fit архетипов по новым терминальным (debounced, non-fatal)
                self._update_terminal_counter()
                self._maybe_autofit()

            except KeyboardInterrupt:
                logger.info("Остановка по Ctrl+C")
                break
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                logger.error("Ошибка в цикле мониторинга: %s", exc)

            time.sleep(interval)

    def cleanup_sources(self) -> int:
        """Убрать из incoming исходники звонков, у которых готов транскрипт.

        Копия уже лежит в архиве (originals/YYYY/MM), поэтому исходник из
        incoming можно удалить. Гейт: ``pipeline.remove_source_on_success``.

        Возвращает число удалённых файлов.
        """
        if not getattr(self.config.pipeline, "remove_source_on_success", True):
            return 0
        if not self._last_sources:
            return 0

        removed = 0
        for call_id, (user_id, root, src_path) in list(self._last_sources.items()):
            call = self.repo.get_call(user_id, call_id)
            if not call:
                continue
            if int(call.get("pipeline_stage", 0) or 0) < _TRANSCRIBED_STAGE:
                continue  # ещё не транскрибирован — оставляем
            self._remove_source(src_path, root)
            removed += 1

        if removed:
            logger.info("Убрано исходников из incoming: %d", removed)
        return removed

    def cleanup_normalized(self) -> int:
        """Снести orphan'ные и «отработанные» normalized .wav.

        Удаляет ТРИ категории:
          1. Сиротские wav (нет call-записи в БД или call принадлежит другому
             пользователю) — мусор после краха до/во время ingest;
          2. Терминальные (done/transcribed/error) или stage>=2 — транскрипция
             уже завершена, wav не нужен (регенерируется из mp3-архива при
             перепрогоне);
          3. Зависшие (status=new/normalizing, stage<2) — НЕ трогаем: они
             нужны для resume (orchestrator пропускает ffmpeg если wav есть).
             Удалятся после обработки через process_pending → _maybe_delete.

        Подстраховка: ловит wav, не удалённые в orchestrator (resume/error/сбой),
        чтобы они не накапливались на больших прогонах.
        """
        if not getattr(self.config.pipeline, "delete_normalized_after_transcribe", False):
            return 0
        terminal = {"done", "transcribed", "error"}
        removed = 0
        for user in self.repo.get_all_users():
            uid = user["user_id"]
            norm_dir = Path(self.config.data_dir) / "users" / uid / "audio" / "normalized"
            if not norm_dir.is_dir():
                continue
            for wav in norm_dir.glob("*.wav"):
                try:
                    call_id = int(wav.stem.split("__", 1)[0])
                except ValueError:
                    continue
                call = self.repo.get_call(uid, call_id)
                if not call:
                    # Сиротский wav: call-записи нет → мусор после краха
                    try:
                        wav.unlink()
                        removed += 1
                        logger.debug(
                            "Удалён сиротский normalized wav: %s (call_id=%d)",
                            wav.name, call_id,
                        )
                    except OSError as exc:
                        logger.warning("Не удалить сиротский normalized %s: %s", wav, exc)
                    continue
                stage = int(call.get("pipeline_stage", 0) or 0)
                if stage >= _TRANSCRIBED_STAGE or call.get("status") in terminal:
                    try:
                        wav.unlink()
                        removed += 1
                    except OSError as exc:
                        logger.warning("Не удалить normalized %s: %s", wav, exc)
        if removed:
            logger.info("Подчищено normalized wav: %d", removed)
        return removed

    # ── Insight autofit (Ф0 плана досье) ───────────────────────────────

    def _update_terminal_counter(self) -> None:
        """Накопить число НОВЫХ терминальных звонков (done/transcribed) с прошлого fit.

        Первый вызов — baseline: исторические звонки не считаются (иначе
        старт watch на БД с 16k done сразу дёргал бы fit).
        """
        conn = self.repo._get_conn()
        for user in self.repo.get_all_users():
            uid = user["user_id"]
            row = conn.execute(
                "SELECT COUNT(*) FROM calls "
                "WHERE user_id = ? AND status IN ('done', 'transcribed')",
                (uid,),
            ).fetchone()
            n = int(row[0] or 0)
            prev = self._terminal_seen.get(uid)
            if prev is not None and n > prev:
                self._new_terminal_since_fit += n - prev
            self._terminal_seen[uid] = n

    def _maybe_autofit(self) -> None:
        """Debounced insight-fit: флаг → порог новых → интервал → запуск.

        Сбой fit НЕ роняет цикл (паттерн pipeline.md Fallback); таймштамп
        обновляется и при сбое — чтобы не спамить ретраями каждый цикл.
        """
        p = self.config.pipeline
        if not getattr(p, "insight_autofit", True):
            return
        min_new = max(1, int(getattr(p, "insight_autofit_min_new", 25)))
        if self._new_terminal_since_fit < min_new:
            return
        now = time.time()
        min_interval = int(getattr(p, "insight_autofit_min_interval_sec", 1800))
        if now - self._last_autofit_ts < min_interval:
            return
        self._last_autofit_ts = now
        try:
            self._run_insight_fit()
            self._new_terminal_since_fit = 0
        except Exception as exc:  # noqa: BLE001 — autofit не должен ронять цикл
            logger.error("Insight autofit упал (продолжаем цикл): %s", exc)

    def _run_insight_fit(self) -> None:
        """features-build + archetypes-fit для всех пользователей (numpy, без GPU)."""
        from callprofiler.insight import cli_ops  # lazy: numpy не нужен циклу

        conn = self.repo._get_conn()
        for user in self.repo.get_all_users():
            uid = user["user_id"]
            n_feats = cli_ops.run_features_build(conn, uid)
            res = cli_ops.run_archetypes_fit(conn, uid)
            # Возраст: маркер-часть инкрементально (stale_only) — новые звонки
            # уточняют оценку; LLM-пасс ЗДЕСЬ запрещён (GPU занят ASR) — только
            # CLI `age-estimate --llm` в LLM-окне.
            age = cli_ops.run_age_estimate(
                conn, uid, use_llm=False, stale_only=True,
                owner_birth_year=getattr(self.config, "owner_birth_year", 0) or 0,
            )
            logger.info(
                "Insight autofit user=%s: features=%d, k=%d, assigned=%d, "
                "age est=%d skip=%d",
                uid, n_feats, res.get("k", 0), res.get("n_assigned", 0),
                age.get("estimated", 0), age.get("skipped_fresh", 0),
            )

    # ── Внутренние методы ──────────────────────────────────────────────

    def _scan_user_dir(self, user_id: str, incoming_path: Path) -> list[int]:
        """Сканировать папку пользователя и зарегистрировать новые файлы.

        Для каждого аудиофайла: MD5 → поиск существующего звонка.
          - звонок есть и транскрибирован (stage>=2) → убрать исходник
            (копия уже в архиве);
          - звонок есть, но НЕ транскрибирован (новый/завис/error) → ОСТАВИТЬ
            (данные не теряем, перезапустится; уберём в следующем цикле, когда
            транскрипт будет готов);
          - звонка нет → ingest_file (регистрация) + запомнить исходник.
        """
        new_ids: list[int] = []
        settle_sec = self.config.pipeline.file_settle_sec
        remove_on_success = getattr(
            self.config.pipeline, "remove_source_on_success", True
        )

        # Рекурсивный обход (с подпапками)
        for root, _dirs, files in os.walk(incoming_path):
            for filename in files:
                filepath = Path(root) / filename

                if filepath.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue

                # Файл ещё пишется → пропустить до следующего цикла
                if not self._is_file_settled(filepath, settle_sec):
                    logger.debug("Файл ещё записывается: %s", filepath)
                    continue

                try:
                    md5 = self._file_md5(filepath)
                except OSError as exc:
                    logger.error("Не удалось прочитать %s: %s", filepath, exc)
                    continue

                existing = self.repo.get_call_by_md5(user_id, md5)
                if existing is not None:
                    stage = int(existing.get("pipeline_stage", 0) or 0)
                    if remove_on_success and stage >= _TRANSCRIBED_STAGE:
                        # Транскрипт готов → убрать исходник из incoming
                        logger.info(
                            "Дубликат транскрибирован, убираю из incoming: %s", filename
                        )
                        self._remove_source(filepath, incoming_path)
                        continue

                    # Не транскрибирован (new/error/normalizing). Если архивная копия
                    # ПОТЕРЯНА (частая причина error после переноса данных) —
                    # восстановить из incoming + сбросить звонок на переобработку.
                    archive = existing.get("audio_path") or ""
                    call_id = existing.get("call_id")
                    if archive and not Path(archive).exists():
                        try:
                            Path(archive).parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(filepath, archive)
                            self.repo.reset_call(call_id)
                            new_ids.append(call_id)
                            self._last_sources[call_id] = (user_id, incoming_path, filepath)
                            logger.info(
                                "Восстановлен потерянный архив + сброс call_id=%s на "
                                "переобработку: %s", call_id, filename,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.error(
                                "Не удалось восстановить архив для %s: %s", filename, exc
                            )
                    else:
                        logger.info(
                            "Уже в БД (call_id=%s, status=%s, stage=%d, архив на месте) "
                            "— не реингестим: %s. Переобработать: "
                            "process \"<файл>\" --user %s --force",
                            call_id, existing.get("status"), stage, filename, user_id,
                        )
                    continue

                try:
                    call_id = self.ingester.ingest_file(user_id, str(filepath))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ошибка при инжесте %s: %s", filepath, exc)
                    continue

                if call_id is not None:
                    new_ids.append(call_id)
                    self._last_sources[call_id] = (user_id, incoming_path, filepath)
                    logger.info(
                        "Зарегистрирован: %s → call_id=%d (user_id=%s)",
                        filename, call_id, user_id,
                    )

        return new_ids

    @staticmethod
    def _file_md5(filepath: Path) -> str:
        """MD5 файла (та же схема, что в Ingester — для дедупликации)."""
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _remove_source(self, src_path: Path, stop_root: Path | None = None) -> None:
        """Удалить исходник из incoming и подчистить пустые подпапки.

        ``stop_root`` — корень incoming: его и всё, что выше, НЕ трогаем.
        """
        try:
            src_path.unlink(missing_ok=True)
            logger.debug("Исходник убран из incoming: %s", src_path)
            self._prune_empty_parents(src_path.parent, stop_root)
        except OSError as exc:
            logger.warning("Не удалось убрать исходник %s: %s", src_path, exc)

    @staticmethod
    def _prune_empty_parents(directory: Path, stop_root: Path | None) -> None:
        """Удалить пустые подпапки внутри incoming. Сам incoming-корень не трогаем."""
        if stop_root is None:
            return
        try:
            stop = Path(stop_root).resolve()
            current = directory.resolve()
            for _ in range(8):  # ограничитель глубины — без бесконечного цикла
                # current должен быть строго ВНУТРИ stop_root, иначе стоп
                if current == stop or stop not in current.parents:
                    break
                if not current.exists() or any(current.iterdir()):
                    break
                current.rmdir()
                current = current.parent
        except OSError:
            pass

    @staticmethod
    def _is_file_settled(filepath: Path, settle_sec: int) -> bool:
        """Проверить что файл не изменялся последние settle_sec секунд.

        settle_sec<=0 → всегда «устоялся» (ждать не нужно; детерминировано,
        без зависимости от точности часов/ФС).
        """
        if settle_sec <= 0:
            return True
        try:
            mtime = filepath.stat().st_mtime
            age = time.time() - mtime
            return age >= settle_sec
        except OSError:
            return False
