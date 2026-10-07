import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def main():
    subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "new.py"),
            "--mode",
            "unsafe",
            "--threads",
            "100",
            "--workers",
            "10",
            "--song-id",
            "31",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()