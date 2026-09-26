# Renders docs/architecture.html (the technical architecture diagram) to
# docs/architecture.png at 2x resolution with headless Microsoft Edge.
# Run: .venv\Scripts\python.exe docs\make_architecture.py
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

with tempfile.TemporaryDirectory() as profile:
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--user-data-dir={profile}", "--force-device-scale-factor=2", "--window-size=2000,1330",
                    "--virtual-time-budget=3000", f"--screenshot={HERE / 'architecture.png'}",
                    (HERE / "architecture.html").resolve().as_uri()], check=True, capture_output=True)
print("wrote", HERE / "architecture.png")
