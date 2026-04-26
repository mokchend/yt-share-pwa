#!/usr/bin/env python3
"""
Khmer Karaoke Pipeline

What it does:
1. Downloads a YouTube video with yt-dlp
2. Extracts audio with ffmpeg
3. Separates vocals / instrumental with Demucs
4. Transcribes vocals with WhisperX (fallback to Whisper)
5. Generates SRT / LRC lyric files
6. Burns subtitles into a karaoke-style preview video with ffmpeg

Notes:
- Khmer ASR quality depends heavily on song clarity and mix quality.
- You will usually need manual correction afterward for production-quality karaoke.
- This script is built to be practical and hackable rather than minimal.

Recommended install (Windows PowerShell):
    py -m pip install yt-dlp openai-whisper
    py -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    py -m pip install demucs whisperx soundfile

System dependencies:
- ffmpeg must be installed and available in PATH
- soundfile (PySoundFile): required so torchaudio can save .wav during Demucs; without it you may get
  "Couldn't find appropriate backend to handle uri ... drums.wav" even with short ASCII paths.

Examples:
    py karaoke_pipeline.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
    py karaoke_pipeline.py "https://www.youtube.com/watch?v=XXXXXXXXXXX" --language km --model small
    py karaoke_pipeline.py "https://www.youtube.com/watch?v=XXXXXXXXXXX" --skip-burn
    py karaoke_pipeline.py "URL" --no-smule-lyrics-link   # omit Smule reference search sidecars
    py karaoke_pipeline.py "URL" --smule-search default  # broad Smule search (full cleaned title)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus


# -----------------------------
# Configuration / data models
# -----------------------------

@dataclass
class PipelinePaths:
    workdir: Path
    downloads: Path
    audio_dir: Path
    stems_dir: Path
    transcripts_dir: Path
    output_dir: Path
    temp_dir: Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


# -----------------------------
# Helpers
# -----------------------------

def print_step(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def run_command(
    command: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    printable = " ".join(shlex_quote(part) for part in command)
    print(f"[CMD] {printable}")
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def shlex_quote(text: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", text):
        return text
    return '"' + text.replace('"', '\\"') + '"'


def ensure_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(
            f"Required tool '{name}' was not found in PATH. Install it first and retry."
        )


def ensure_torchaudio_wav_save_backend() -> None:
    """
    Demucs writes stems with torchaudio.save(). Many torchaudio builds on Windows
    have no built-in WAV writer unless PySoundFile is installed.
    """
    try:
        import soundfile  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Missing package: soundfile (PySoundFile). Demucs needs it so torchaudio can save .wav. "
            "Install with:\n  py -m pip install soundfile\n"
            "Then rerun the pipeline."
        ) from exc


def default_inference_device() -> str:
    """Use CUDA only when this PyTorch build reports a usable GPU (not merely nvidia-smi on PATH)."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def resolve_inference_device(requested: str) -> str:
    """If --device cuda was passed but PyTorch is CPU-only, fall back to cpu."""
    try:
        import torch
    except Exception:
        return requested
    if requested == "cuda" or requested.startswith("cuda:"):
        if not torch.cuda.is_available():
            print(
                "[WARN] --device cuda but torch.cuda.is_available() is False "
                "(CPU-only PyTorch, e.g. torch from pytorch.org/*+cpu). Using cpu."
            )
            return "cpu"
    return requested


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_file_by_exact_name(directory: Path, basename: str) -> Path | None:
    """
    Locate a file by exact filename. Prefer this over Path.glob(name) when basename
    may contain '[]' — glob treats brackets as character-class syntax and often matches nothing.
    """
    for candidate in directory.iterdir():
        if candidate.is_file() and candidate.name == basename:
            return candidate
    return None


def slugify(text: str, max_len: int = 80) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-zA-Z0-9\-_. ]+", "", text)
    text = re.sub(r"\s+", "-", text)
    text = text.strip("-._")
    if not text:
        text = "karaoke-project"
    return text[:max_len]


def safe_tooling_stem(video_path: Path) -> str:
    """
    Basename (no extension) safe for Demucs / torchaudio on Windows: avoid Unicode,
    U+29F8 slashes in titles, and square brackets — torchaudio often fails with those URIs.
    yt-dlp titles usually include the 11-char id as [videoId] somewhere; prefer the last match.
    """
    stem = video_path.stem
    id_matches = list(re.finditer(r"\[([A-Za-z0-9_-]{11})\]", stem))
    if id_matches:
        return id_matches[-1].group(1)
    slug = slugify(stem)
    if slug and slug != "karaoke-project":
        return slug
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:16]
    return f"track-{digest}"


_KHMER_RE = re.compile(r"[\u1780-\u17FF]")


def channel_noise_hits(text: str) -> int:
    """Penalize channel / promo fragments when guessing the song title."""
    low = text.lower()
    return sum(
        1
        for hint in (
            "subscribe",
            "records",
            " music",
            "channel",
            "productions",
            "youtube",
            "home of music",
            "facebook",
            "instagram",
        )
        if hint in low
    )


def extract_smule_song_query(video_stem: str) -> str:
    """
    Infer a concise song title from yt-dlp-style YouTube filenames for Smule search.
    Heuristics: strip trailing [id] and (Official MV) tails, split on ⧸ (common in Khmer titles),
    prefer Khmer-heavy segments, then split on em/en dash or hyphen and score chunks by
    Khmer presence, low channel-noise, and length.
    """
    t = video_stem.strip()
    t = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", t).strip()
    t = re.sub(
        r"\s*[(（][^)）]*\b(official|audio|\bmv\b|lyrics?|\bvideo\b|hd|4k|live)\b[^)）]*[)）]\s*$",
        "",
        t,
        flags=re.I,
    ).strip()

    if "⧸" in t:
        parts = [re.sub(r"\s+", " ", p.strip()) for p in t.split("⧸")]
        parts = [p for p in parts if p]
        if parts:
            if _KHMER_RE.search(parts[0]) and len(parts[0]) >= 2:
                return parts[0]
            return max(
                parts,
                key=lambda p: (bool(_KHMER_RE.search(p)), -channel_noise_hits(p), len(p)),
            )

    for sep in (" — ", " – ", " - "):
        if sep in t:
            chunks = [re.sub(r"\s+", " ", c.strip()) for c in t.split(sep)]
            chunks = [c for c in chunks if c]
            if len(chunks) >= 2:
                return max(
                    chunks,
                    key=lambda c: (bool(_KHMER_RE.search(c)), -channel_noise_hits(c), len(c)),
                )

    if "|" in t:
        return re.sub(r"\s+", " ", t.split("|", 1)[0].strip())

    return re.sub(r"\s+", " ", t.replace("/", " ").strip())


def build_smule_search_url(video_stem: str, *, search_mode: str) -> str:
    """
    Smule search URLs (reference only). ``lyrics`` mode uses an inferred title plus ``ct=1`` on
    https://www.smule.com/search (lyrics-oriented tab on the web UI); ``default`` uses the full
    cleaned title with a broad search.
    """
    if search_mode == "lyrics":
        q = extract_smule_song_query(video_stem)
        if not q:
            q = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", video_stem).strip()
        if not re.search(r"(?i)lyric", q) and not _KHMER_RE.search(q):
            q = f"{q} lyrics"
        return f"https://www.smule.com/search?ct=1&q={quote_plus(q)}"
    if search_mode != "default":
        raise ValueError(f"Unknown --smule-search mode: {search_mode!r}")
    q = video_stem.strip()
    q = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", q).strip()
    q = q.replace("⧸", " ").replace("/", " ").strip()
    q = re.sub(r"\s+", " ", q)
    if not q:
        q = video_stem.strip()
    return f"https://www.smule.com/search?q={quote_plus(q)}"


def write_smule_lyrics_sidecar_files(
    output_dir: Path,
    smule_url: str,
    *,
    search_mode: str,
    inferred_query: str | None,
) -> tuple[Path, Path]:
    """Plain-text URL plus Windows Internet Shortcut for one-click open."""
    txt_path = output_dir / "smule-lyrics-search.txt"
    url_path = output_dir / "smule-lyrics-search.url"
    mode_line = (
        f"Smule search mode: {search_mode} (lyrics = inferred title + ct=1; default = full title).\n"
    )
    infer_line = (
        f"Inferred song query for Smule: {inferred_query}\n" if inferred_query else ""
    )
    write_text(
        txt_path,
        mode_line
        + infer_line
        + "Open in browser (Smule reference / community karaoke):\n"
        f"{smule_url}\n",
    )
    url_path.write_text(f"[InternetShortcut]\nURL={smule_url}\n", encoding="ascii", errors="strict")
    return txt_path, url_path


def sec_to_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    secs = ms // 1000
    ms %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def sec_to_lrc_time(seconds: float) -> str:
    total_centis = int(round(seconds * 100))
    minutes = total_centis // 6000
    centis_rest = total_centis % 6000
    secs = centis_rest // 100
    centis = centis_rest % 100
    return f"[{minutes:02d}:{secs:02d}.{centis:02d}]"


def clean_lyric_text(text: str) -> str:
    text = text.replace("♪", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# -----------------------------
# Folder setup
# -----------------------------

def build_paths(base_dir: Path) -> PipelinePaths:
    return PipelinePaths(
        workdir=ensure_dir(base_dir),
        downloads=ensure_dir(base_dir / "01_download"),
        audio_dir=ensure_dir(base_dir / "02_audio"),
        stems_dir=ensure_dir(base_dir / "03_stems"),
        transcripts_dir=ensure_dir(base_dir / "04_transcripts"),
        output_dir=ensure_dir(base_dir / "05_output"),
        temp_dir=ensure_dir(base_dir / "tmp"),
    )


# -----------------------------
# YouTube download
# -----------------------------

def download_youtube_video(url: str, downloads_dir: Path) -> Path:
    print_step("1) Downloading YouTube video")
    output_template = str(downloads_dir / "%(title).200s [%(id)s].%(ext)s")

    run_command(
        [
            "yt-dlp",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            url,
        ]
    )

    mp4_files = sorted(downloads_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4_files:
        raise FileNotFoundError("No MP4 file found after download.")

    video_path = mp4_files[0]
    print(f"[OK] Downloaded video: {video_path}")
    return video_path


# -----------------------------
# Audio extraction
# -----------------------------

def extract_audio(video_path: Path, audio_dir: Path, output_stem: str | None = None) -> Path:
    print_step("2) Extracting audio")
    stem = output_stem if output_stem is not None else video_path.stem
    audio_path = audio_dir / f"{stem}.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(audio_path),
        ]
    )
    print(f"[OK] Audio extracted: {audio_path}")
    return audio_path


# -----------------------------
# Stem separation
# -----------------------------

def run_demucs(audio_path: Path, stems_dir: Path, demucs_model: str) -> tuple[Path, Path]:
    print_step("3) Separating vocals and instrumental")
    ensure_torchaudio_wav_save_backend()

    run_command(
        [
            sys.executable,
            "-m",
            "demucs.separate",
            "-n",
            demucs_model,
            # Default 4-stem mode writes drums/bass/other — not no_vocals.wav. Karaoke needs instrumental.
            "--two-stems",
            "vocals",
            "-o",
            str(stems_dir),
            str(audio_path),
        ]
    )

    separated_root = stems_dir / demucs_model / audio_path.stem
    vocals = separated_root / "vocals.wav"
    instrumental = separated_root / "no_vocals.wav"

    if not vocals.exists():
        raise FileNotFoundError(f"Vocals stem not found: {vocals}")
    if not instrumental.exists():
        raise FileNotFoundError(f"Instrumental stem not found: {instrumental}")

    print(f"[OK] Vocals: {vocals}")
    print(f"[OK] Instrumental: {instrumental}")
    return vocals, instrumental


# -----------------------------
# Transcription
# -----------------------------

def whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401
        return True
    except Exception:
        return False


def transcribe_with_whisperx(
    audio_path: Path,
    transcripts_dir: Path,
    language: str,
    model_name: str,
    device: str,
    batch_size: int,
    compute_type: str,
) -> list[TranscriptSegment]:
    print_step("4) Transcribing vocals with WhisperX")
    import whisperx

    if device == "cpu" and compute_type == "float16":
        compute_type = "float32"
        print("[INFO] WhisperX on CPU: using compute_type=float32 (float16 is for GPU).")

    audio = whisperx.load_audio(str(audio_path))
    model = whisperx.load_model(model_name, device, compute_type=compute_type, language=language)
    result = model.transcribe(audio, batch_size=batch_size)

    segments = result.get("segments", [])

    try:
        align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
        aligned = whisperx.align(segments, align_model, metadata, audio, device)
        segments = aligned.get("segments", segments)
        print("[OK] Alignment completed.")
    except Exception as exc:
        print(f"[WARN] Alignment skipped: {exc}")

    normalized: list[TranscriptSegment] = []
    for seg in segments:
        text = clean_lyric_text(seg.get("text", ""))
        if not text:
            continue
        normalized.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=text,
            )
        )

    json_path = transcripts_dir / f"{audio_path.stem}.whisperx.json"
    write_text(
        json_path,
        json.dumps(
            [{"start": s.start, "end": s.end, "text": s.text} for s in normalized],
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"[OK] WhisperX JSON saved: {json_path}")
    return normalized


def transcribe_with_whisper(
    audio_path: Path,
    transcripts_dir: Path,
    language: str,
    model_name: str,
) -> list[TranscriptSegment]:
    print_step("4) Transcribing vocals with Whisper fallback")
    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=language)
    segments = result.get("segments", [])

    normalized: list[TranscriptSegment] = []
    for seg in segments:
        text = clean_lyric_text(seg.get("text", ""))
        if not text:
            continue
        normalized.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=text,
            )
        )

    json_path = transcripts_dir / f"{audio_path.stem}.whisper.json"
    write_text(
        json_path,
        json.dumps(
            [{"start": s.start, "end": s.end, "text": s.text} for s in normalized],
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"[OK] Whisper JSON saved: {json_path}")
    return normalized


# -----------------------------
# Subtitle writers
# -----------------------------

def write_srt(segments: Iterable[TranscriptSegment], output_path: Path) -> Path:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{sec_to_srt_time(seg.start)} --> {sec_to_srt_time(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    write_text(output_path, "\n".join(lines))
    return output_path


def write_lrc(segments: Iterable[TranscriptSegment], output_path: Path) -> Path:
    lines = [f"{sec_to_lrc_time(seg.start)}{seg.text}" for seg in segments]
    write_text(output_path, "\n".join(lines))
    return output_path


def write_txt(segments: Iterable[TranscriptSegment], output_path: Path) -> Path:
    lines = [seg.text for seg in segments]
    write_text(output_path, "\n".join(lines))
    return output_path


# -----------------------------
# Karaoke preview burn-in
# -----------------------------

def copy_srt_for_ffmpeg_subtitles_filter(srt_path: Path, output_video: Path) -> Path:
    """
    ffmpeg's subtitles filter parses '[]' and commas inside the path as filter syntax.
    Copy the SRT next to the preview output using an ASCII-only basename (YouTube id when present).
    """
    stem = srt_path.stem
    id_matches = list(re.finditer(r"\[([A-Za-z0-9_-]{11})\]", stem))
    if id_matches:
        tag = id_matches[-1].group(1)
    else:
        tag = hashlib.sha1(str(srt_path).encode("utf-8")).hexdigest()[:12]
    safe = output_video.parent / f"{tag}.ffmpeg-subtitles.srt"
    shutil.copy2(srt_path, safe)
    return safe


def burn_preview_video(
    source_video: Path,
    instrumental_audio: Path,
    srt_path: Path,
    output_video: Path,
) -> Path:
    print_step("5) Rendering karaoke preview video")
    safe_srt = copy_srt_for_ffmpeg_subtitles_filter(srt_path, output_video)
    try:
        # subtitles= treats ":" as option separators; absolute Windows paths (C:\...) break parsing.
        # Run ffmpeg with cwd=output dir and pass only the ASCII filename for the filter.
        subtitles_filter = f"subtitles={safe_srt.name}"
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_video),
                "-i",
                str(instrumental_audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                subtitles_filter,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_video),
            ],
            cwd=output_video.parent,
        )
    finally:
        try:
            safe_srt.unlink(missing_ok=True)
        except OSError:
            pass

    print(f"[OK] Preview video created: {output_video}")
    return output_video


# -----------------------------
# Report / UX
# -----------------------------

def write_report(
    report_path: Path,
    video_path: Path,
    vocals_path: Path,
    instrumental_path: Path,
    srt_path: Path,
    lrc_path: Path,
    txt_path: Path,
    preview_video_path: Path | None,
    smule_lyrics_url: str | None = None,
    smule_search_mode: str | None = None,
    smule_inferred_query: str | None = None,
) -> None:
    parts = [
        textwrap.dedent(
            f"""
            Khmer Karaoke Pipeline Report
            ============================

            Source video:
            {video_path}

            Generated files:
            - Vocals stem: {vocals_path}
            - Instrumental stem: {instrumental_path}
            - Subtitle SRT: {srt_path}
            - Lyric LRC: {lrc_path}
            - Plain lyrics TXT: {txt_path}
            - Preview video: {preview_video_path if preview_video_path else 'Skipped'}
            """
        ).strip(),
    ]
    if smule_lyrics_url:
        meta = ""
        if smule_search_mode:
            meta += f"Search mode: {smule_search_mode}\n"
        if smule_inferred_query:
            meta += f"Inferred song title for query: {smule_inferred_query}\n"
        parts.append(
            textwrap.dedent(
                f"""
                Reference lyrics (Smule)
                --------------------------
                {meta}{smule_lyrics_url}
                Open in a browser to find community karaoke versions and compare lyrics (manual reference).
                Sidecar files: smule-lyrics-search.txt, smule-lyrics-search.url
                """
            ).strip()
        )
    parts.append(
        textwrap.dedent(
            """
            Suggested next step:
            Open the .srt in Aegisub for manual cleanup and better karaoke timing.
            """
        ).strip()
    )
    write_text(report_path, "\n\n".join(parts) + "\n")


# -----------------------------
# CLI
# -----------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local Khmer karaoke pipeline from a YouTube URL.")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--project-name", default="", help="Optional custom project folder name")
    parser.add_argument("--base-dir", default="karaoke_projects", help="Base folder for outputs")
    parser.add_argument("--language", default="km", help="Transcription language code. Default: km")
    parser.add_argument("--model", default="small", help="Whisper/WhisperX model name. Example: base, small, medium")
    parser.add_argument(
        "--device",
        default=default_inference_device(),
        help="Inference device: cuda or cpu (default: cuda only if torch.cuda.is_available())",
    )
    parser.add_argument("--compute-type", default="float16", help="WhisperX compute type. Example: float16, int8, float32")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--demucs-model", default="htdemucs", help="Demucs model name")
    parser.add_argument("--skip-burn", action="store_true", help="Skip preview video render")
    parser.add_argument(
        "--no-smule-lyrics-link",
        action="store_true",
        help="Do not write Smule reference-lyrics search URL (report + smule-lyrics-search.* sidecars).",
    )
    parser.add_argument(
        "--smule-search",
        choices=("lyrics", "default"),
        default="lyrics",
        help="Smule: 'lyrics' = inferred song title + lyrics-oriented search (ct=1 on smule.com/search). "
        "'default' = broad search using the full cleaned YouTube title.",
    )
    return parser.parse_args()


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    args = parse_args()
    args.device = resolve_inference_device(args.device)

    ensure_tool("ffmpeg")
    ensure_tool("yt-dlp")

    project_slug = slugify(args.project_name) if args.project_name else ""
    if not project_slug:
        project_slug = "khmer-karaoke-project"

    base_root = ensure_dir(Path(args.base_dir).resolve())
    project_dir = base_root / project_slug
    paths = build_paths(project_dir)

    print_step("Khmer Karaoke Pipeline")
    print(f"Project folder: {paths.workdir}")
    print(f"Language: {args.language}")
    print(f"Whisper model: {args.model}")
    print(f"Device: {args.device}")

    video_path = download_youtube_video(args.url, paths.downloads)

    # Improve folder naming after download if user did not provide a project name.
    if project_slug == "khmer-karaoke-project":
        derived_slug = slugify(video_path.stem)
        better_project_dir = base_root / derived_slug
        if better_project_dir != paths.workdir and not better_project_dir.exists():
            shutil.move(str(paths.workdir), str(better_project_dir))
            paths = build_paths(better_project_dir)
            # Refresh path after move (do not use glob(filename): YouTube IDs in [...] break glob)
            relocated = find_file_by_exact_name(paths.downloads, video_path.name)
            if relocated is not None:
                video_path = relocated
            else:
                raise FileNotFoundError(
                    f"After renaming project folder, could not find {video_path.name!r} under {paths.downloads}."
                )

    tooling_stem = safe_tooling_stem(video_path)
    if tooling_stem != video_path.stem:
        print(
            f"[INFO] Using ASCII-safe working basename for ffmpeg / Demucs / torch: {tooling_stem!r} "
            f"(original title kept for .srt / .lrc / preview names)."
        )
    audio_path = extract_audio(video_path, paths.audio_dir, output_stem=tooling_stem)
    vocals_path, instrumental_path = run_demucs(audio_path, paths.stems_dir, args.demucs_model)

    if whisperx_available():
        segments = transcribe_with_whisperx(
            audio_path=vocals_path,
            transcripts_dir=paths.transcripts_dir,
            language=args.language,
            model_name=args.model,
            device=args.device,
            batch_size=args.batch_size,
            compute_type=args.compute_type,
        )
    else:
        print("[WARN] whisperx not available. Falling back to openai-whisper.")
        segments = transcribe_with_whisper(
            audio_path=vocals_path,
            transcripts_dir=paths.transcripts_dir,
            language=args.language,
            model_name=args.model,
        )

    if not segments:
        raise RuntimeError("No transcript segments were generated.")

    srt_path = write_srt(segments, paths.output_dir / f"{video_path.stem}.srt")
    lrc_path = write_lrc(segments, paths.output_dir / f"{video_path.stem}.lrc")
    txt_path = write_txt(segments, paths.output_dir / f"{video_path.stem}.lyrics.txt")

    preview_video_path: Path | None = None
    if not args.skip_burn:
        preview_video_path = burn_preview_video(
            source_video=video_path,
            instrumental_audio=instrumental_path,
            srt_path=srt_path,
            output_video=paths.output_dir / f"{video_path.stem}.karaoke-preview.mp4",
        )

    smule_url: str | None = None
    smule_inferred: str | None = None
    if not args.no_smule_lyrics_link:
        if args.smule_search == "lyrics":
            smule_inferred = extract_smule_song_query(video_path.stem)
            print(f"[INFO] Smule inferred song query: {smule_inferred!r}")
        smule_url = build_smule_search_url(video_path.stem, search_mode=args.smule_search)
        smule_txt, smule_url_file = write_smule_lyrics_sidecar_files(
            paths.output_dir,
            smule_url,
            search_mode=args.smule_search,
            inferred_query=smule_inferred,
        )
        print(f"[INFO] Smule search ({args.smule_search}): {smule_url}")
        print(f"[INFO] Saved {smule_txt.name} and {smule_url_file.name} in output folder.")

    write_report(
        report_path=paths.output_dir / "report.txt",
        video_path=video_path,
        vocals_path=vocals_path,
        instrumental_path=instrumental_path,
        srt_path=srt_path,
        lrc_path=lrc_path,
        txt_path=txt_path,
        preview_video_path=preview_video_path,
        smule_lyrics_url=smule_url,
        smule_search_mode=args.smule_search if smule_url else None,
        smule_inferred_query=smule_inferred,
    )

    print_step("Done")
    print(f"Output folder: {paths.output_dir}")
    print(f"SRT: {srt_path}")
    print(f"LRC: {lrc_path}")
    print(f"Lyrics TXT: {txt_path}")
    if preview_video_path:
        print(f"Preview video: {preview_video_path}")
    if smule_url:
        print(f"Smule lyrics search: {smule_url}")
    print("Tip: open the SRT in Aegisub to manually fix Khmer lyric timing and text.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[ABORTED] Interrupted by user.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        raise SystemExit(1)
