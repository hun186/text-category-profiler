"""Local Windows Stage 4 candidate manual acceptance, isolated and read-only.

Invoked by the root BAT using an explicit venv and exact upstream SHA.
This does not assert human visual acceptance; it records the user's verdict.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHA = "3e9355851357326ac0e47848b8cef64b50bf1b83"

CHECKS = (
    "01 Stage 4 viewer-only loads on one port, without the model/WorkPool",
    "02 Selecting TW Affairs and Load shows all FIVE layout modes",
    "03 Full network, hierarchy, and Louvain mode visibly render correctly",
    "04 Louvain community click expands; clicking a member can re-collapse",
    "05 Search and Filter/Color/Size work and do not corrupt the graph",
    "06 Switching to full network restores original node IDs and directed arrows",
    "07 No disruptive camera jumps, excessive scrollbars or unreadable labels",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8098)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    if os.environ.get("JAAL_STAGE4_COMMUNITY_CANDIDATE") != "1":
        parser.error("opt-in candidate environment variable must equal 1")
    from BertScript.jaal_original_mount import _community_candidate_enabled
    if not _community_candidate_enabled():
        parser.error("candidate installation did not pass exact SHA verification")
    url = f"http://127.0.0.1:{args.port}/"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = Path(tempfile.mkdtemp(prefix="stage4-jaal-candidate-"))
    log_path = directory / "stage4-server.log"
    report = {
        "schema": "stage4_jaal_candidate_manual_acceptance_v1",
        "candidate_sha": SHA,
        "python": sys.version.split()[0],
        "mode": "viewer_only_no_models",
        "port": args.port,
        "verdict": "INCOMPLETE",
        "checks": list(CHECKS),
    }
    process = None
    try:
        with log_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "BertScript" / "Test_result_Vis.py"),
                 "--viewer-only", "-p", str(args.port)],
                cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
                env=dict(os.environ),
            )
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Stage 4 server exited with code {process.returncode}; see log"
                    )
                try:
                    with urlopen(url + "_dash-layout", timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, URLError):
                    time.sleep(0.5)
            else:
                raise RuntimeError("Stage 4 localhost did not become ready")
            print("\nOpen Stage 4 at", url)
            webbrowser.open(url)
            print("Select TW Affairs and click Load Jaal; verify the five modes.")
            print("Human desktop acceptance checklist:")
            for item in CHECKS:
                print(" -", item)
            value = input("\nType PASS, FAIL or INCOMPLETE after inspection: ").strip().upper()
            report["verdict"] = value if value in {
                "PASS", "FAIL", "INCOMPLETE"
            } else "INCOMPLETE"
    except (OSError, RuntimeError) as exc:
        report["error"] = str(exc)
        print("Acceptance could not finish:", exc, file=sys.stderr)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        report["server_exit_code"] = process.returncode if process else None
        report_file = directory / "acceptance-summary.json"
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        zip_path = ROOT / f"stage4-jaal-candidate-acceptance-{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in (report_file, log_path):
                if path.is_file():
                    archive.write(path, arcname=path.name)
        print("\nDiagnostic ZIP:", zip_path)
        print("Only upload the ZIP if you choose to share its local diagnostic log.")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
