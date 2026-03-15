# SCUE — EDM Music Structure Analyzer

FastAPI server that analyzes EDM tracks and returns section labels (drops, builds, breakdowns, etc.) with beat grid and confidence scores.

## Run

```bash
cd /Users/brach/Documents/DjTools/scue
source .venv/bin/activate
pip install -r requirements.txt   # only needed once or when deps change
uvicorn app:app --reload --port 8000
```

Then open **http://localhost:8000** and drop in an EDM track.

### Model weights (first-time or fresh clone)

The app expects **all-in-one-mlx** harmonix weights in `mlx-weights/`. If you see “Could not find MLX weights for harmonix-fold0”, run:

```bash
python scripts/download_mlx_weights.py
```

This downloads the pre-converted weights from the [all-in-one-mlx](https://github.com/ssmall256/all-in-one-mlx) repo.

---

## How the analysis works

1. **allin1-mlx** runs ML inference → BPM, beats, downbeats, generic segment labels.
2. **librosa** extracts RMS energy, spectral centroid/flux, chroma, MFCCs, tempogram.
3. **ruptures** (KernelCPD with RBF kernel) finds change points in the stacked feature matrix.
4. **Merge**: allin1 segments are primary; ruptures boundaries that don’t match add sub-divisions.
5. **EDM classification**: heuristics remap labels:
   - **chorus** → **drop** (high energy + bass-heavy)
   - Rising energy + centroid before a drop → **build**
   - Brief energy dip between build and drop → **fakeout**
   - **break/bridge** → **breakdown**
6. Quantize all boundaries to nearest downbeat.
7. Confidence scored by allin1 + ruptures agreement.

---

## Testing & accuracy

- **Ground truth**: Pick 10–20 tracks across sub-genres (house, dubstep, trance, DnB) and manually annotate sections (e.g. in a spreadsheet). Compare predicted vs. actual.
- **Tune parameters**: The ruptures penalty is exposed as a query param on `/api/analyze` (e.g. `?penalty=5.0`). Start at 5.0; lower for more boundaries.
- **Energy thresholds** in `analyzer/edm_classifier.py` (e.g. 1.2× for drops, 0.6× for fakeouts) will need sub-genre tuning — dubstep drops are more extreme than house drops.
- **Edge cases**: tracks with no clear drop, multiple drops in succession, long ambient intros, tempo changes.
- **Future**: use allin1’s embeddings for section similarity, train a lightweight classifier on annotated data, add sub-genre detection to auto-adjust thresholds.
