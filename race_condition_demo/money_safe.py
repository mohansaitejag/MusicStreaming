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
            "money",
            "--mode",
            "locked",
            "--threads",
            "100",
            "--workers",
            "10",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()