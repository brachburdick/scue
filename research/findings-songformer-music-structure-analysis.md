# Research Findings: SongFormer — Transformer-Based Music Structure Analysis

**Source:** https://huggingface.co/ASLP-lab/SongFormer
**Date:** 2026-03-23
**Status:** Evaluated (not integrated)

---

## Executive Summary

| Topic | Key Finding | Implication |
|-------|------------|-------------|
| **What it does** | Segments audio into labeled structural sections (verse, chorus, bridge, intro, outro, etc.) with start/end timestamps | Automatic structure annotation — replaces manual tagging or rekordbox memory cues for section identification |
| **Architecture** | Transformer-based, multi-resolution self-supervised audio representations, heterogeneous supervision | Modern approach; quality likely exceeds older rule-based segmenters |
| **Input/Output** | Audio waveform (24kHz) → JSON array of `{start, end, label}` segments | Clean output format, easy to integrate as a Layer 1 analysis step |
| **Availability** | HuggingFace model + GitHub repo (ASLP-lab/SongFormer), paper arXiv 2510.02797 | Open weights, can run locally |
| **Hardware** | Requires CUDA GPU for inference | Not viable on CPU-only setups; M-series Mac would need MPS or ONNX port |

---

## What SongFormer Does

SongFormer performs **music structure analysis (MSA)** — given an audio file, it identifies segment boundaries and assigns semantic labels:

```json
[
  {"start": 0.0,   "end": 15.2,  "label": "intro"},
  {"start": 15.2,  "end": 45.8,  "label": "verse"},
  {"start": 45.8,  "end": 76.3,  "label": "chorus"},
  {"start": 76.3,  "end": 107.1, "label": "verse"}
]
```

Labels include: intro, verse, chorus, bridge, outro, instrumental, and potentially others depending on the training data.

## Technical Details

- **Model type:** Transformer with multi-resolution self-supervised representations
- **Input:** Raw audio waveform at 24,000 Hz sampling rate (WAV or numpy/tensor)
- **Training data:** SongFormDB (large-scale, multi-genre dataset built by the authors)
- **Benchmark:** SongFormBench (high-quality, human-annotated benchmark for fair comparison)
- **Paper:** arXiv 2510.02797

### Usage

```python
from transformers import AutoModel
from huggingface_hub import snapshot_download
import sys, os

local_dir = snapshot_download(
    repo_id="ASLP-lab/SongFormer",
    repo_type="model",
    ignore_patterns=["SongFormer.pt", "SongFormer.safetensors"],
)
sys.path.append(local_dir)
os.environ["SONGFORMER_LOCAL_DIR"] = local_dir

songformer = AutoModel.from_pretrained(local_dir, trust_remote_code=True)
songformer.to("cuda:0").eval()

result = songformer("path/to/audio.wav")
```

**Note:** Requires `trust_remote_code=True` — the model includes custom code.

## SCUE Relevance

### Where It Fits

- **Layer 1 (offline analysis):** Run SongFormer as a post-analysis enrichment step. Output structure labels alongside existing beat grid, key, energy, and section data.
- **Complements allin1:** allin1-mlx already does structure segmentation. SongFormer could serve as a second opinion or replacement if it proves more accurate on DJ music (electronic, 4-on-the-floor, extended mixes).
- **Cue generation (Layer 2):** Structure labels directly inform cue decisions — a chorus transition warrants different lighting than a verse-to-verse transition.

### Concerns

| Concern | Detail |
|---------|--------|
| **CUDA requirement** | SCUE runs on macOS (Apple Silicon). Would need MPS backend port or ONNX conversion. No macOS support out of the box. |
| **`trust_remote_code`** | Runs arbitrary code from the HF repo. Needs audit before use. |
| **24kHz resampling** | SCUE analysis pipeline works at 44.1kHz/48kHz. Would need a resample step. |
| **Overlap with allin1** | allin1-mlx already provides structure segmentation. Need to evaluate whether SongFormer adds meaningful accuracy improvement to justify the added dependency. |
| **Windows compat** | CUDA is available on Windows, so this is actually better than allin1-mlx (which is Apple-only). Could be the Windows-compatible alternative for structure analysis. |

### Potential Windows Story

SongFormer could be the **Windows-compatible replacement for allin1-mlx's structure analysis**:
- allin1-mlx: Apple Silicon only (MLX backend)
- SongFormer: CUDA (Windows + Linux native, macOS needs work)

A dual-backend approach where macOS uses allin1-mlx and Windows uses SongFormer for the same task could solve the platform parity problem for structure analysis.

## Next Steps (if pursued)

1. Run SongFormer on a few tracks from the SCUE test collection and compare output to allin1 structure labels
2. Evaluate accuracy on electronic/DJ music specifically (most MSA models are trained on pop/rock)
3. Test MPS backend compatibility on Apple Silicon
4. Benchmark inference time per track
5. If viable, define integration point in Layer 1 analysis pipeline

## References

- HuggingFace: https://huggingface.co/ASLP-lab/SongFormer
- GitHub: https://github.com/ASLP-lab/SongFormer
- Paper: https://arxiv.org/abs/2510.02797
- HuggingFace Space (demo): https://huggingface.co/spaces/ASLP-lab/SongFormer
