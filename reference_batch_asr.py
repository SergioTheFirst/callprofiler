#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_asr.py - Massovaya rasshifrovka zvonkov po rolyam
faster-whisper large-v3 + Pyannote 3.3.2 + reference embedding
"""

import os, sys, time, tempfile, subprocess, warnings
import numpy as np
import torch
import soundfile as sf
import librosa
from pathlib import Path

warnings.filterwarnings("ignore")

# Fix torch 2.6 weights_only issue
import torch as _torch
_original_load = _torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_load(*args, **kwargs)
_torch.load = _patched_load

# =====================================================
#   NASTROJKI
# =====================================================
AUDIO_FOLDER  = r"C:\calls\audio"      # papka s audio (+ podpapki)
REF_AUDIO     = r"C:\pro\mbot\ref\manager.wav"  # etalon golosa menedzhera
OUTPUT_FOLDER = r"C:\calls\out"        # kuda pisat .txt

REF_NAME      = "Me"
OTHER_NAME    = "S2"
HF_TOKEN      = "TOKEN"            # token HuggingFace


WHISPER_MODEL = "large-v3"
AUDIO_EXTS    = {".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".flac", ".amr", ".aac"}
# =====================================================


def convert_to_wav(src, dst):
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", dst
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_whisper(device):
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    print("  Loading faster-whisper large-v3 ...")
    model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute,
                         cpu_threads=8, num_workers=2)
    print("  OK")
    return model


def load_pyannote():
    from pyannote.audio import Pipeline, Model, Inference
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("  Loading pyannote/embedding ...")
    emb_model = Model.from_pretrained("pyannote/embedding", use_auth_token="TOKEN")
    inference = Inference(emb_model, window="whole")
    inference.to(dev)
    print("  Loading pyannote/speaker-diarization-3.1 ...")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token="TOKEN")
    pipeline.to(dev)
    print("  OK")
    return inference, pipeline


def get_embedding(inference, wav_path):
    emb = np.array(inference(wav_path)).squeeze()
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 1e-9 else emb


def build_ref_embedding(inference, ref_path):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        ref_wav = tmp.name
    try:
        convert_to_wav(ref_path, ref_wav)
        emb = get_embedding(inference, ref_wav)
    finally:
        if os.path.exists(ref_wav):
            os.remove(ref_wav)
    print(f"  Reference embedding ready (dim={emb.shape[0]})")
    return emb


def transcribe(whisper_model, wav_path):
    segments, info = whisper_model.transcribe(
        wav_path,
        language="ru",
        beam_size=5,
        best_of=5,
        temperature=0,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=400,
            speech_pad_ms=200,
            threshold=0.5
        ),
        word_timestamps=True,
        condition_on_previous_text=True,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
    )
    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end":   seg.end,
            "text":  seg.text.strip()
        })
    return result


def diarize(wav_path, ref_emb, inference, pipeline):
    diarization = pipeline(wav_path, min_speakers=2, max_speakers=2)

    raw = {}
    for turn, _, lbl in diarization.itertracks(yield_label=True):
        if turn.duration >= 0.4:
            raw.setdefault(lbl, []).append((round(turn.start, 3), round(turn.end, 3)))

    if not raw:
        return []

    wav_full, sr = librosa.load(wav_path, sr=16000, mono=True)
    label_emb = {}
    for lbl, segs in raw.items():
        chunks = [wav_full[int(s*sr):int(e*sr)] for s, e in segs
                  if int(e*sr) > int(s*sr)]
        if not chunks:
            continue
        tmp_path = os.path.join(tempfile.gettempdir(), f"spk_{lbl}_{os.getpid()}.wav")
        try:
            sf.write(tmp_path, np.concatenate(chunks), sr)
            emb = get_embedding(inference, tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        label_emb[lbl] = emb

    ref_lbl = max(label_emb, key=lambda l: float(np.dot(label_emb[l], ref_emb)))
    sim = float(np.dot(label_emb[ref_lbl], ref_emb))
    print(f"   {ref_lbl} -> {REF_NAME} (sim={sim:.3f})")

    result = []
    for lbl, segs in raw.items():
        spk = REF_NAME if lbl == ref_lbl else OTHER_NAME
        for s, e in segs:
            result.append({"s": s, "e": e, "speaker": spk})
    return sorted(result, key=lambda x: x["s"])


def assign_speakers(w_segs, d_segs):
    tagged = []
    for seg in w_segs:
        ws, we = seg["start"], seg["end"]
        best_spk, best_ov = None, 0.0
        for d in d_segs:
            ov = max(0.0, min(we, d["e"]) - max(ws, d["s"]))
            if ov > best_ov:
                best_ov, best_spk = ov, d["speaker"]
        
        # Если нет перекрытия — берём ближайшего спикера по времени
        if best_spk is None:
            closest = min(d_segs, key=lambda d: min(abs(ws - d["e"]), abs(we - d["s"])))
            best_spk = closest["speaker"]
        
        tagged.append({**seg, "speaker": best_spk})
    return tagged

def save_txt(out_path, tagged):
    os.makedirs(Path(out_path).parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        prev_spk = None
        for seg in tagged:
            spk = seg.get("speaker", "Unknown")
            txt = seg.get("text", "").strip()
            if not txt:
                continue
            if spk != prev_spk:
                if prev_spk is not None:
                    f.write("\n")
                f.write(f"\n[{spk}]: {txt}")
                prev_spk = spk
            else:
                f.write(f" {txt}")
        f.write("\n")


def process_file(audio_path, out_path, whisper_model, inference, pipeline, ref_emb):
    if os.path.exists(out_path):
        print(f"   skip (exists): {Path(out_path).name}")
        return True

    t0 = time.time()
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        print("   -> converting ...")
        convert_to_wav(audio_path, wav_path)

        print("   -> transcribing ...")
        w_segs = transcribe(whisper_model, wav_path)
        print(f"      segments: {len(w_segs)}")

        if not w_segs:
            print("   ! empty transcript, skipping")
            return False

        print("   -> diarizing ...")
        d_segs = diarize(wav_path, ref_emb, inference, pipeline)

        tagged = assign_speakers(w_segs, d_segs)
        save_txt(out_path, tagged)
        print(f"   OK [{round(time.time()-t0, 1)}s] -> {Path(out_path).name}")
        return True

    except subprocess.CalledProcessError:
        print("   ! ffmpeg error")
        return False
    except Exception as e:
        print(f"   ! error: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


def collect_files(folder):
    result = []
    for root, dirs, files in os.walk(folder):
        for f in sorted(files):
            if Path(f).suffix.lower() in AUDIO_EXTS:
                result.append(os.path.join(root, f))
    return sorted(result)


def main():
    print("=" * 55)
    print("  BATCH ASR: faster-whisper + pyannote")
    print("=" * 55)

    if not os.path.isdir(AUDIO_FOLDER):
        sys.exit(f"Not found AUDIO_FOLDER: {AUDIO_FOLDER}")
    if not os.path.isfile(REF_AUDIO):
        sys.exit(f"Not found REF_AUDIO: {REF_AUDIO}")
    if "VASHTOKEN" in HF_TOKEN:
        sys.exit("Set HF_TOKEN in script settings")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {device.upper()}")
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    print("\n[Loading models]")
    whisper_model = load_whisper(device)
    inference, pipeline = load_pyannote()

    print("\n[Building reference embedding]")
    ref_emb = build_ref_embedding(inference, REF_AUDIO)

    audio_files = collect_files(AUDIO_FOLDER)
    if not audio_files:
        sys.exit(f"No audio files in: {AUDIO_FOLDER}")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    print(f"\n  Source : {AUDIO_FOLDER}")
    print(f"  Output : {OUTPUT_FOLDER}")
    print(f"  Files  : {len(audio_files)}")
    print()

    ok = fail = 0
    log_path = os.path.join(OUTPUT_FOLDER, "_log.txt")
    log_file = open(log_path, "a", encoding="utf-8")
    import datetime
    log_file.write(f"\n=== Запуск {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    for i, ap in enumerate(audio_files, 1):
        # Сохраняем структуру подпапок в выходной директории
        rel = os.path.relpath(ap, AUDIO_FOLDER)
        out = str(Path(OUTPUT_FOLDER) / Path(rel).with_suffix(".txt"))
        print(f"[{i}/{len(audio_files)}] {rel}")
        t_start = time.time()
        success = process_file(ap, out, whisper_model, inference, pipeline, ref_emb)
        elapsed = round(time.time() - t_start, 1)
        status = "OK" if success else "FAIL"
        size_kb = round(os.path.getsize(ap) / 1024)
        log_file.write(f"{status} | {elapsed}s | {size_kb}kb | {rel}\n")
        log_file.flush()
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n{'='*55}")
    print(f"  Done: {ok}   Errors: {fail}")

    log_file.write(f"=== Итог: OK={ok} FAIL={fail} ===\n")

    log_file.close()
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
