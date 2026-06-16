import sys
import subprocess
from pathlib import Path

if __name__ == "__main__":
    app_path = Path(__file__).parent / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), *sys.argv[1:]],
        check=True,
    )