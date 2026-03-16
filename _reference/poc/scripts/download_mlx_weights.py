#!/usr/bin/env python3
"""Download harmonix MLX weights from all-in-one-mlx repo into mlx-weights/."""

import urllib.request
from pathlib import Path

BASE = "https://github.com/ssmall256/all-in-one-mlx/raw/main/mlx-weights"
FILES = []
for i in range(8):
    FILES.append(f"harmonix-fold{i}_mlx.npz")
    FILES.append(f"harmonix-fold{i}_mlx.yaml")


def main():
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "mlx-weights"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        url = f"{BASE}/{name}"
        path = out_dir / name
        if path.is_file():
            print(f"Skip (exists): {name}")
            continue
        print(f"Downloading: {name}")
        urllib.request.urlretrieve(url, path)

    print("Done. mlx-weights/ is ready.")


if __name__ == "__main__":
    main()
