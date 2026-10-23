#!/usr/bin/env python3
"""ClamAV control helper for the Omarchy bar plugin.

Commands print a single JSON status object on stdout. Scan/update work runs in
the background and continuously rewrites the shared status file so the shell
widget can show live progress.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ID = "glink.clamav"
REMINDER_DAYS = 7
STALE_DAYS = 3
STATUS_VERSION = 1
CVD_NAMES = ("daily.cvd", "daily.cld", "main.cvd", "main.cld", "bytecode.cvd", "bytecode.cld")
def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    path = Path(base) / "omarchy" / "clamav"
    path.mkdir(parents=True, exist_ok=True)
    return path


def status_path() -> Path:
    return state_dir() / "status.json"


def pid_path() -> Path:
    return state_dir() / "worker.pid"


def log_path() -> Path:
    return state_dir() / "last-scan.log"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def empty_scan() -> dict:
    return {
        "running": False,
        "target": "",
        "label": "",
        "filesTotal": 0,
        "filesDone": 0,
        "infected": 0,
        "errors": 0,
        "percent": 0,
        "currentFile": "",
        "startedAt": "",
        "finishedAt": "",
        "infectedFiles": [],
        "summary": "",
        "exitCode": None,
    }


def empty_status() -> dict:
    return {
        "version": STATUS_VERSION,
        "phase": "idle",
        "updatedAt": now_iso(),
        "scan": empty_scan(),
        "database": {
            "path": "/var/lib/clamav",
            "ageHours": None,
            "ageDays": None,
            "lastUpdatedAt": "",
            "stale": False,
            "reminderDue": False,
            "updating": False,
            "lastUpdateOk": None,
            "lastUpdateAt": "",
            "lastUpdateMessage": "",
            "remindedAt": "",
        },
        "daemon": {
            "active": False,
            "freshclamActive": False,
            "enabled": False,
            "freshclamEnabled": False,
        },
        "install": {
            "packageInstalled": False,
            "binariesPresent": False,
            "databasePresent": False,
            "ready": False,
            "needsInstall": True,
            "needsConfigure": False,
            "installing": False,
            "lastInstallOk": None,
            "lastInstallAt": "",
            "lastInstallMessage": "",
        },
        "lastError": "",
    }


def read_status() -> dict:
    path = status_path()
    if not path.exists():
        return empty_status()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_status()
    if not isinstance(data, dict):
        return empty_status()
    base = empty_status()
    base.update({k: data.get(k, base[k]) for k in base})
    scan = empty_scan()
    scan.update(data.get("scan") or {})
    base["scan"] = scan
    db = base["database"]
    db.update(data.get("database") or {})
    base["database"] = db
    daemon = base["daemon"]
    daemon.update(data.get("daemon") or {})
    base["daemon"] = daemon
    install = base["install"]
    install.update(data.get("install") or {})
    base["install"] = install
    return base


def write_status(status: dict) -> None:
    status = dict(status)
    status["updatedAt"] = now_iso()
    status["version"] = STATUS_VERSION
    path = status_path()
    # Unique temp name avoids races when the scan worker and status polls write together.
    tmp = path.with_name(f".status.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def unit_active(unit: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except OSError:
        return False


def unit_enabled(unit: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except OSError:
        return False


def package_installed() -> bool:
    try:
        proc = subprocess.run(
            ["pacman", "-Q", "clamav"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if proc.returncode == 0:
            return True
    except OSError:
        pass
    return Path("/usr/bin/clamscan").exists() and Path("/usr/bin/freshclam").exists()


def binaries_present() -> bool:
    return Path("/usr/bin/clamscan").exists() and Path("/usr/bin/freshclam").exists()


def db_mtime() -> float | None:
    root = Path("/var/lib/clamav")
    newest = None
    for name in CVD_NAMES:
        path = root / name
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def refresh_install_fields(status: dict) -> dict:
    install = status.setdefault("install", empty_status()["install"])
    pkg = package_installed()
    bins = binaries_present()
    mtime = db_mtime()
    db_present = mtime is not None
    daemon_active = unit_active("clamav-daemon.service") or unit_active("clamav-daemon.socket")
    freshclam_active = unit_active("clamav-freshclam.service")
    daemon_enabled = unit_enabled("clamav-daemon.service") or unit_enabled("clamav-daemon.socket")
    freshclam_enabled = unit_enabled("clamav-freshclam.service")

    ready = bool(pkg and bins and db_present and daemon_active and freshclam_active)
    needs_install = not (pkg and bins)
    needs_configure = (pkg and bins) and not ready

    # Preserve in-flight install flags/messages from the worker.
    installing = bool(install.get("installing"))
    install.update(
        {
            "packageInstalled": pkg,
            "binariesPresent": bins,
            "databasePresent": db_present,
            "ready": ready,
            "needsInstall": needs_install,
            "needsConfigure": needs_configure,
            "installing": installing,
            "lastInstallOk": install.get("lastInstallOk"),
            "lastInstallAt": install.get("lastInstallAt") or "",
            "lastInstallMessage": install.get("lastInstallMessage") or "",
        }
    )
    status["install"] = install
    status["daemon"] = {
        "active": daemon_active,
        "freshclamActive": freshclam_active,
        "enabled": daemon_enabled,
        "freshclamEnabled": freshclam_enabled,
    }
    return status


def refresh_database_fields(status: dict, notify: bool = False) -> dict:
    status = refresh_install_fields(status)
    db = status["database"]
    install = status["install"]
    mtime = db_mtime()

    if not install.get("packageInstalled"):
        db["ageHours"] = None
        db["ageDays"] = None
        db["lastUpdatedAt"] = ""
        db["stale"] = False
        db["reminderDue"] = False
    elif mtime is None:
        db["ageHours"] = None
        db["ageDays"] = None
        db["lastUpdatedAt"] = ""
        db["stale"] = True
        db["reminderDue"] = True
    else:
        age_sec = max(0.0, time.time() - mtime)
        age_hours = age_sec / 3600.0
        age_days = age_sec / 86400.0
        db["ageHours"] = round(age_hours, 2)
        db["ageDays"] = round(age_days, 2)
        db["lastUpdatedAt"] = datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds")
        db["stale"] = age_days >= STALE_DAYS
        db["reminderDue"] = age_days >= REMINDER_DAYS

    if notify and db.get("reminderDue") and not db.get("remindedAt") and install.get("ready"):
        send_reminder(db)
        db["remindedAt"] = now_iso()
    elif not db.get("reminderDue"):
        db["remindedAt"] = ""

    return status


def send_reminder(db: dict) -> None:
    age = db.get("ageDays")
    age_text = f"{age:.0f} days old" if isinstance(age, (int, float)) else "out of date"
    body = f"Virus definitions are {age_text}. Open ClamAV in the bar to update."
    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=ClamAV",
                "--urgency=normal",
                "--icon=security-medium",
                "ClamAV definitions need updating",
                body,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def worker_alive() -> bool:
    path = pid_path()
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def clear_worker_pid() -> None:
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass


def write_worker_pid() -> None:
    pid_path().write_text(str(os.getpid()) + "\n", encoding="utf-8")


def expand_target(raw: str) -> Path:
    path = Path(os.path.expanduser(raw)).resolve()
    if not path.exists():
        raise FileNotFoundError(f"scan target not found: {path}")
    return path


def iter_files(target: Path):
    if target.is_file():
        yield target
        return
    for root, dirs, files in os.walk(target, followlinks=False):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for name in files:
            yield Path(root) / name


def count_files(target: Path) -> int:
    total = 0
    for _ in iter_files(target):
        total += 1
        if total > 500_000:
            break
    return total


def shorten(path: str, limit: int = 64) -> str:
    home = str(Path.home())
    text = path
    if text.startswith(home):
        text = "~" + text[len(home) :]
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1) :]


def parse_scan_line(line: str) -> tuple[str | None, str | None]:
    text = line.strip()
    if not text or text.startswith("Scanning ") or text.startswith("-"):
        return None, None
    if "FOUND" in text and not text.endswith("OK"):
        # e.g. "/path: Win.Trojan.X FOUND"
        if text.endswith(" FOUND"):
            path = text[: -len(" FOUND")].rsplit(":", 1)[0].strip()
            return path, "infected"
    if text.endswith(": OK"):
        return text[: -len(": OK")], "ok"
    if ": Empty file" in text or text.endswith(" Empty file"):
        path = text.split(":", 1)[0].strip()
        return path, "ok"
    if text.endswith(" ERROR") or ": Can't " in text:
        path = text.split(":", 1)[0].strip()
        return path, "error"
    return None, None


def run_scan(target_raw: str, label: str) -> int:
    if worker_alive():
        status = refresh_database_fields(read_status())
        status["lastError"] = "A scan or update is already running"
        write_status(status)
        print(json.dumps(status))
        return 1

    status = refresh_database_fields(read_status())
    if not status["install"].get("ready"):
        status["lastError"] = "ClamAV is not installed or configured yet"
        write_status(status)
        print(json.dumps(status))
        return 1

    target = expand_target(target_raw)
    scan = empty_scan()
    scan.update(
        {
            "running": True,
            "target": str(target),
            "label": label or shorten(str(target)),
            "filesTotal": 0,
            "startedAt": now_iso(),
        }
    )
    status["phase"] = "scanning"
    status["scan"] = scan
    status["lastError"] = ""
    write_status(status)

    # Detach into background so the QML Process call returns quickly with status.
    if os.fork() != 0:
        # Parent: wait briefly for child to write first progress, then print status.
        time.sleep(0.15)
        print(json.dumps(refresh_database_fields(read_status())))
        return 0

    # Child worker
    os.setsid()
    write_worker_pid()
    try:
        _scan_worker(target, label)
    finally:
        clear_worker_pid()
    os._exit(0)


def _scan_worker(target: Path, label: str) -> None:
    status = refresh_database_fields(read_status())
    scan = status["scan"]
    files = list(iter_files(target))
    total = len(files)
    scan["filesTotal"] = total
    write_status(status)

    use_daemon = status["daemon"]["active"] and Path("/usr/bin/clamdscan").exists()
    infected_files: list[str] = []
    done = 0
    infected = 0
    errors = 0
    worst_exit = 0
    last_write = 0.0
    cancelled = False

    def publish(current: str, force: bool = False) -> None:
        nonlocal last_write
        now = time.time()
        if not force and now - last_write < 0.2:
            return
        percent = int(min(100, (done / total) * 100)) if total else 100
        scan.update(
            {
                "filesDone": done,
                "filesTotal": total,
                "infected": infected,
                "errors": errors,
                "percent": percent,
                "currentFile": shorten(current, 72) if current else "",
                "infectedFiles": infected_files[:50],
            }
        )
        status["scan"] = scan
        status["phase"] = "scanning"
        write_status(status)
        last_write = now

    def handle_line(raw: str, logf) -> None:
        nonlocal done, infected, errors
        logf.write(raw)
        path, kind = parse_scan_line(raw)
        if path is None:
            return
        # Directory-level OK lines (clamdscan quirk) don't advance per-file counts.
        if kind == "ok" and Path(path).is_dir():
            return
        done += 1
        if kind == "infected":
            infected += 1
            if path not in infected_files:
                infected_files.append(path)
        elif kind == "error":
            errors += 1
        publish(path, force=(kind == "infected"))

    try:
        with log_path().open("w", encoding="utf-8") as logf:
            if total == 0:
                logf.write("No files to scan.\n")
            elif use_daemon:
                batch_size = 40
                for start in range(0, total, batch_size):
                    if not pid_path().exists():
                        cancelled = True
                        break
                    batch = files[start : start + batch_size]
                    cmd = ["clamdscan", "--fdpass", "--verbose", "--", *[str(p) for p in batch]]
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    assert proc.stdout is not None
                    for raw in proc.stdout:
                        handle_line(raw, logf)
                    code = proc.wait()
                    worst_exit = max(worst_exit, code)
                    # If clamdscan only ACK'd the batch as a whole, advance by batch size.
                    if done < start + len(batch):
                        done = min(total, start + len(batch))
                        publish(str(batch[-1]), force=True)
            else:
                cmd = ["clamscan", "--verbose", "--recursive=yes", "--", str(target)]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for raw in proc.stdout:
                    if not pid_path().exists():
                        cancelled = True
                        proc.terminate()
                        break
                    handle_line(raw, logf)
                code = proc.wait()
                worst_exit = max(worst_exit, code)
    except OSError as exc:
        status = refresh_database_fields(read_status())
        status["phase"] = "error"
        status["lastError"] = str(exc)
        status["scan"]["running"] = False
        status["scan"]["finishedAt"] = now_iso()
        write_status(status)
        return

    status = refresh_database_fields(read_status())
    scan = status["scan"]
    if cancelled:
        scan.update(
            {
                "running": False,
                "filesDone": done,
                "filesTotal": total,
                "infected": infected,
                "errors": errors,
                "percent": int(min(100, (done / total) * 100)) if total else 0,
                "currentFile": "",
                "finishedAt": now_iso(),
                "infectedFiles": infected_files[:50],
                "exitCode": worst_exit,
                "summary": "Scan cancelled",
                "label": label or shorten(str(target)),
                "target": str(target),
            }
        )
        status["scan"] = scan
        status["phase"] = "idle"
        status["lastError"] = ""
        write_status(status)
        return

    scan.update(
        {
            "running": False,
            "filesDone": done if done else total,
            "filesTotal": total,
            "infected": infected,
            "errors": errors,
            "percent": 100,
            "currentFile": "",
            "finishedAt": now_iso(),
            "infectedFiles": infected_files[:50],
            "exitCode": worst_exit,
            "summary": (
                f"{infected} infected · {total} scanned"
                if infected
                else f"Clean · {total} scanned"
            ),
            "label": label or shorten(str(target)),
            "target": str(target),
        }
    )
    status["scan"] = scan
    if infected > 0:
        status["phase"] = "infected"
        status["lastError"] = ""
        try:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=ClamAV",
                    "--urgency=critical",
                    "--icon=security-high",
                    "ClamAV found threats",
                    f"{infected} infected file(s) under {shorten(str(target))}",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    elif worst_exit not in (0, 1):
        # clamdscan/clamscan: 0 clean, 1 infected, 2+ error
        status["phase"] = "error"
        status["lastError"] = f"Scan failed (exit {worst_exit}). See {log_path()}"
    else:
        status["phase"] = "idle"
        status["lastError"] = ""
        try:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=ClamAV",
                    "--urgency=low",
                    "--icon=security-high",
                    "ClamAV scan finished",
                    scan["summary"] + f" · {shorten(str(target))}",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    write_status(status)


def stop_worker() -> int:
    status = refresh_database_fields(read_status())
    if not pid_path().exists():
        status["phase"] = "idle"
        status["scan"]["running"] = False
        status["database"]["updating"] = False
        status["install"]["installing"] = False
        write_status(status)
        print(json.dumps(status))
        return 0
    pid = None
    try:
        pid = int(pid_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    clear_worker_pid()
    status["phase"] = "idle"
    status["scan"]["running"] = False
    status["scan"]["finishedAt"] = now_iso()
    status["scan"]["summary"] = "Scan cancelled"
    status["database"]["updating"] = False
    status["install"]["installing"] = False
    status["lastError"] = ""
    write_status(status)
    print(json.dumps(status))
    return 0


def run_update() -> int:
    if worker_alive():
        status = refresh_database_fields(read_status())
        status["lastError"] = "A scan or update is already running"
        write_status(status)
        print(json.dumps(status))
        return 1

    status = refresh_database_fields(read_status())
    if not status["install"].get("packageInstalled"):
        status["lastError"] = "ClamAV is not installed — use Install & configure first"
        write_status(status)
        print(json.dumps(status))
        return 1

    status["phase"] = "updating"
    status["database"]["updating"] = True
    status["lastError"] = ""
    write_status(status)

    if os.fork() != 0:
        time.sleep(0.1)
        print(json.dumps(refresh_database_fields(read_status())))
        return 0

    os.setsid()
    write_worker_pid()
    helper = Path(__file__).resolve().parent / "update-helper.sh"
    try:
        proc = subprocess.run(
            ["pkexec", str(helper)],
            check=False,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        message = (proc.stdout or proc.stderr or "").strip()
        if len(message) > 280:
            message = message[-280:]
    except OSError as exc:
        ok = False
        message = str(exc)

    status = refresh_database_fields(read_status())
    db = status["database"]
    db["updating"] = False
    db["lastUpdateOk"] = ok
    db["lastUpdateAt"] = now_iso()
    db["lastUpdateMessage"] = message or ("Updated" if ok else "Update failed")
    if ok:
        db["remindedAt"] = ""
        status["phase"] = "idle"
        status["lastError"] = ""
        try:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=ClamAV",
                    "--urgency=low",
                    "--icon=security-high",
                    "ClamAV definitions updated",
                    "Virus database refresh finished.",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    else:
        status["phase"] = "error"
        status["lastError"] = message or "Database update failed"
    status["database"] = db
    status = refresh_database_fields(status)
    write_status(status)
    clear_worker_pid()
    os._exit(0)


def run_install() -> int:
    if worker_alive():
        status = refresh_database_fields(read_status())
        status["lastError"] = "A scan or update is already running"
        write_status(status)
        print(json.dumps(status))
        return 1

    status = refresh_database_fields(read_status())
    if status["install"].get("ready"):
        status["lastError"] = ""
        status["install"]["lastInstallMessage"] = "ClamAV is already installed and configured"
        status["install"]["lastInstallOk"] = True
        write_status(status)
        print(json.dumps(status))
        return 0

    status["phase"] = "installing"
    status["install"]["installing"] = True
    status["lastError"] = ""
    write_status(status)

    if os.fork() != 0:
        time.sleep(0.1)
        print(json.dumps(refresh_database_fields(read_status())))
        return 0

    os.setsid()
    write_worker_pid()
    helper = Path(__file__).resolve().parent / "install-helper.sh"
    try:
        proc = subprocess.run(
            ["pkexec", str(helper)],
            check=False,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        message = (proc.stdout or proc.stderr or "").strip()
        if len(message) > 400:
            message = message[-400:]
    except OSError as exc:
        ok = False
        message = str(exc)

    status = refresh_database_fields(read_status())
    install = status["install"]
    install["installing"] = False
    install["lastInstallOk"] = ok
    install["lastInstallAt"] = now_iso()
    install["lastInstallMessage"] = message or (
        "ClamAV installed and configured" if ok else "Install failed"
    )
    status["install"] = install
    status = refresh_database_fields(status)

    if ok and status["install"].get("ready"):
        status["phase"] = "idle"
        status["lastError"] = ""
        try:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=ClamAV",
                    "--urgency=low",
                    "--icon=security-high",
                    "ClamAV is ready",
                    "Package installed, definitions downloaded, services enabled.",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
    elif ok:
        status["phase"] = "error"
        status["lastError"] = (
            "Install finished but ClamAV is not fully ready yet. "
            + (install.get("lastInstallMessage") or "Check services and try Configure again.")
        )
    else:
        status["phase"] = "error"
        status["lastError"] = message or "ClamAV install failed"

    write_status(status)
    clear_worker_pid()
    os._exit(0)


def cmd_status(notify: bool) -> int:
    status = refresh_database_fields(read_status(), notify=notify)
    if status["scan"].get("running") and not worker_alive():
        status["scan"]["running"] = False
        if status["phase"] == "scanning":
            status["phase"] = "error"
            status["lastError"] = "Scan worker exited unexpectedly"
    if status["database"].get("updating") and not worker_alive():
        status["database"]["updating"] = False
        if status["phase"] == "updating":
            status["phase"] = "error"
            status["lastError"] = "Update worker exited unexpectedly"
    if status["install"].get("installing") and not worker_alive():
        status["install"]["installing"] = False
        if status["phase"] == "installing":
            status["phase"] = "error"
            status["lastError"] = "Install worker exited unexpectedly"
    # Keep the setup phase visible while ClamAV still needs attention.
    if (
        status["phase"] in ("idle", "error")
        and not status["install"].get("ready")
        and not status["install"].get("installing")
        and not status["scan"].get("running")
        and not status["database"].get("updating")
    ):
        if status["phase"] != "error" or not status.get("lastError"):
            status["phase"] = "setup"
    write_status(status)
    print(json.dumps(status))
    return 0


def cmd_ack_reminder() -> int:
    status = refresh_database_fields(read_status())
    status["database"]["remindedAt"] = now_iso()
    write_status(status)
    print(json.dumps(status))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Omarchy ClamAV plugin control")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Print current status JSON")
    p_status.add_argument("--notify", action="store_true", help="Emit reminder notification if due")

    p_scan = sub.add_parser("scan", help="Start a recursive scan")
    p_scan.add_argument("target", help="File or directory to scan")
    p_scan.add_argument("--label", default="", help="Short label for the UI")

    sub.add_parser("stop", help="Stop a running scan/update worker")
    sub.add_parser("update", help="Refresh virus definitions via pkexec")
    sub.add_parser("install", help="Install and configure ClamAV via pkexec")
    sub.add_parser("ack-reminder", help="Mark the current reminder as acknowledged")

    args = parser.parse_args()
    try:
        if args.command == "status":
            return cmd_status(notify=args.notify)
        if args.command == "scan":
            return run_scan(args.target, args.label)
        if args.command == "stop":
            return stop_worker()
        if args.command == "update":
            return run_update()
        if args.command == "install":
            return run_install()
        if args.command == "ack-reminder":
            return cmd_ack_reminder()
    except FileNotFoundError as exc:
        status = refresh_database_fields(read_status())
        status["phase"] = "error"
        status["lastError"] = str(exc)
        write_status(status)
        print(json.dumps(status))
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any failure to the widget
        status = refresh_database_fields(read_status())
        status["phase"] = "error"
        status["lastError"] = str(exc)
        write_status(status)
        print(json.dumps(status))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
