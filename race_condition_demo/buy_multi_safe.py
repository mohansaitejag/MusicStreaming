import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def main():
    subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "tx_demo.py"),
            "--demo",
            "buy",
            "--scenario",
            "multi-user",
            "--mode",
            "locked",
            "--threads",
            "6",
            "--workers",
            "6",
            "--song-id",
            "31",
            "--user-ids",
            "1,2,3,4,5",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()