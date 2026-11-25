import multiprocessing
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    from ok.cli import main as cli_main

    sys.argv = ["ok", "mcp", "--config", "config:config"] + sys.argv[1:]
    cli_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
