#!/usr/bin/env python3
"""
================================================================================
Python IT Automation Suite
================================================================================
One file, four tools for IT automation.
Ein Datei, vier Tools für IT-Automation.
Один файл, четыре инструмента для IT-автоматизации.

Author:  Timofey Vishnevskiy
Purpose: Praktikum als Fachinformatiker (Anwendungsentwicklung) in Deutschland
License: MIT
================================================================================

Quick start:
    python automation_suite.py --help

Modules:
    backup-gdrive     Backup to Google Drive
    backup-dropbox    Backup to Dropbox
    password-check    Password strength audit + HTML/CSV/JSON report
    email-remind      Send templated email reminders
"""

import argparse
import csv
import json
import logging
import os
import re
import shutil
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional, Dict, Any

# ------------------------------------------------------------------------------
# Optional dependencies handling
# ------------------------------------------------------------------------------
_MISSING = []

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None
    _MISSING.append("python-dotenv")

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None
    _MISSING.append("pyyaml")

# Google Drive
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
    _HAS_GDRIVE = True
except Exception:  # pragma: no cover
    _HAS_GDRIVE = False

# Dropbox
try:
    import dropbox
    from dropbox.files import WriteMode
    _HAS_DROPBOX = True
except Exception:  # pragma: no cover
    _HAS_DROPBOX = False


# ------------------------------------------------------------------------------
# Bootstrap: load .env and config
# ------------------------------------------------------------------------------
def _bootstrap() -> Dict[str, Any]:
    if load_dotenv:
        load_dotenv()
    else:
        logging.warning("python-dotenv not installed. Create .env file and export vars manually.")

    cfg_path = Path("config.yaml")
    if yaml and cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


CONFIG = _bootstrap()


def _cfg(key: str, default: Any = None) -> Any:
    """Fetch nested config key via dot-notation, e.g. 'email.smtp_server'."""
    val = CONFIG
    for part in key.split("."):
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
    return val if val is not None else default


# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
def _setup_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _die(msg: str, code: int = 1) -> None:
    logging.error(msg)
    sys.exit(code)


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        _die(f"Environment variable {name} is not set. Check .env file.")
    return val


def _require_deps(names: List[str]) -> None:
    for n in names:
        if n in _MISSING:
            _die(f"Missing dependency: {n}. Run: pip install -r requirements.txt")


# ==============================================================================
# MODULE 1: GOOGLE DRIVE BACKUP
# ==============================================================================
def run_backup_gdrive(args: argparse.Namespace) -> None:
    """Backup local folders to Google Drive with folder structure preserved."""
    if not _HAS_GDRIVE:
        _die("Google Drive dependencies missing. pip install google-auth google-auth-oauthlib google-api-python-client")

    _require_deps(["pyyaml"])

    folders = args.folders or _cfg("gdrive.folders", ["./documents", "./projects"])
    exclude = args.exclude or _cfg("gdrive.exclude", ["*.tmp", "*.log", ".git", "__pycache__", ".env", "node_modules"])
    creds_file = Path(args.credentials or _cfg("gdrive.credentials_file", "credentials.json"))
    token_file = Path(args.token or _cfg("gdrive.token_file", "token.json"))

    if not creds_file.exists():
        _die(
            f"Google credentials file not found: {creds_file}\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download JSON and save as credentials.json"
        )

    SCOPES = ["https://www.googleapis.com/auth/drive"]
    backup_name = args.name or ("backup_" + datetime.now().strftime("%Y-%m-%d_%H-%M"))

    def get_service() -> Any:
        creds = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
                if args.headless:
                    creds = flow.run_console()
                else:
                    creds = flow.run_local_server(port=0)
            with token_file.open("w", encoding="utf-8") as token:
                token.write(creds.to_json())
        return build("drive", "v3", credentials=creds, static_discovery=False)

    def create_folder(service: Any, name: str, parent: Optional[str] = None) -> str:
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent] if parent else [],
        }
        return service.files().create(body=meta, fields="id").execute()["id"]

    def upload_file(service: Any, path: Path, parent: str) -> None:
        media = MediaFileUpload(str(path), resumable=True)
        meta = {"name": path.name, "parents": [parent]}
        service.files().create(body=meta, media_body=media, fields="id").execute()

    def backup(service: Any, local_path: Path, drive_parent: str, name: str) -> int:
        fid = create_folder(service, name, drive_parent)
        count = 0
        for root, dirs, files in os.walk(local_path):
            # filter excluded dirs to avoid descending into them
            dirs[:] = [d for d in dirs if not any(Path(d).match(x) for x in exclude)]
            rel = Path(root).relative_to(local_path)
            cur = fid
            if rel != Path("."):
                for p in rel.parts:
                    cur = create_folder(service, p, cur)
            for f in files:
                fp = Path(root) / f
                if any(fp.match(x) for x in exclude):
                    continue
                try:
                    upload_file(service, fp, cur)
                    count += 1
                    logging.info("[OK] %s", fp)
                except Exception as exc:
                    logging.error("[ERR] %s: %s", fp, exc)
        return count

    svc = get_service()
    root_id = create_folder(svc, backup_name)
    total = 0
    for folder in folders:
        p = Path(folder).expanduser().resolve()
        if not p.exists():
            logging.warning("Skipping missing folder: %s", p)
            continue
        name = p.name or str(p)
        logging.info("Backup folder: %s", p)
        total += backup(svc, p, root_id, name)
    logging.info("Done. Total files uploaded: %d", total)


# ==============================================================================
# MODULE 2: DROPBOX BACKUP
# ==============================================================================
def run_backup_dropbox(args: argparse.Namespace) -> None:
    """Backup local folders to Dropbox preserving directory structure."""
    if not _HAS_DROPBOX:
        _die("Dropbox dependency missing. pip install dropbox")

    token = args.token or os.getenv("DROPBOX_TOKEN") or _cfg("dropbox.token")
    if not token:
        _die(
            "DROPBOX_TOKEN not set.\n"
            "1. Go to https://www.dropbox.com/developers/apps\n"
            "2. Create app + generate access token\n"
            "3. Add to .env: DROPBOX_TOKEN=your_token"
        )

    folders = args.folders or _cfg("dropbox.folders", ["./documents", "./projects"])
    exclude = args.exclude or _cfg("dropbox.exclude", ["*.tmp", "*.log", ".git", "__pycache__", ".env"])
    backup_name = args.name or ("backup_" + datetime.now().strftime("%Y-%m-%d_%H-%M"))
    dropbox_base = (args.path or "/Backups") + "/" + backup_name
    CHUNK = 4 * 1024 * 1024

    dbx = dropbox.Dropbox(token)
    try:
        dbx.files_create_folder_v2(dropbox_base)
        logging.info("Created Dropbox folder: %s", dropbox_base)
    except dropbox.exceptions.ApiError:
        logging.info("Dropbox folder already exists: %s", dropbox_base)

    def upload_file(local_path: Path, dropbox_path: str) -> None:
        size = local_path.stat().st_size
        with local_path.open("rb") as f:
            if size <= CHUNK:
                dbx.files_upload(f.read(), dropbox_path, mode=WriteMode("overwrite"))
            else:
                session = dbx.files_upload_session_start(f.read(CHUNK))
                cursor = dropbox.files.UploadSessionCursor(
                    session_id=session.session_id, offset=f.tell()
                )
                commit = dropbox.files.CommitInfo(path=dropbox_path, mode=WriteMode("overwrite"))
                while f.tell() < size:
                    remaining = size - f.tell()
                    chunk = f.read(CHUNK if remaining > CHUNK else remaining)
                    if remaining <= CHUNK:
                        dbx.files_upload_session_finish(chunk, cursor, commit)
                    else:
                        dbx.files_upload_session_append_v2(chunk, cursor)
                        cursor.offset = f.tell()

    def backup_folder(local_path: Path, base_path: str) -> int:
        uploaded = 0
        for root, dirs, files in os.walk(local_path):
            dirs[:] = [d for d in dirs if not any(Path(d).match(x) for x in exclude)]
            rel = Path(root).relative_to(local_path)
            rel_str = "/".join(rel.parts) if rel != Path(".") else ""
            for file in files:
                lf = Path(root) / file
                if any(lf.match(x) for x in exclude):
                    continue
                dp = f"{base_path}/{rel_str}/{file}".replace("\\", "/").replace("//", "/")
                try:
                    upload_file(lf, dp)
                    uploaded += 1
                    logging.info("[OK] %s", lf)
                except Exception as exc:
                    logging.error("[ERR] %s: %s", lf, exc)
        return uploaded

    total = 0
    for folder in folders:
        p = Path(folder).expanduser().resolve()
        if not p.exists():
            logging.warning("Skipping missing folder: %s", p)
            continue
        name = p.name or str(p)
        logging.info("Backup folder: %s", p)
        total += backup_folder(p, f"{dropbox_base}/{name}")
    logging.info("Done. Total files uploaded: %d", total)


# ==============================================================================
# MODULE 3: PASSWORD CHECKER + REPORT
# ==============================================================================
@dataclass
class CheckResult:
    employee_id: str
    name: str
    email: str
    password_masked: str
    length: int
    has_upper: bool
    has_lower: bool
    has_digit: bool
    has_special: bool
    has_common: bool
    has_repeats: bool
    has_sequence: bool
    score: int
    strength: str
    issues: List[str]
    recommendations: List[str]


def run_password_check(args: argparse.Namespace) -> None:
    """Audit password strength from CSV and generate HTML/CSV/JSON reports."""
    min_length = args.min_length or _cfg("password.min_length", 8)
    min_score = args.min_score or _cfg("password.min_score", 60)
    input_csv = Path(args.input or _cfg("password.input_csv", "employees.csv"))
    output_dir = Path(args.output or _cfg("password.output_dir", "password_reports"))

    COMMON = {
        "password", "123456", "12345678", "qwerty", "abc123", "monkey",
        "letmein", "dragon", "111111", "baseball", "iloveyou", "trustno1",
        "sunshine", "princess", "admin", "welcome", "shadow", "ashley",
        "football", "jesus", "michael", "ninja", "mustang", "password1",
        "123456789", "adobe123", "admin123", "login", "master", "photoshop",
        "1q2w3e4r", "zaq12wsx", "qwertyuiop", "lovely", "whatever",
    }

    SEQUENCES = [
        "abcdefghijklmnopqrstuvwxyz", "zyxwvutsrqponmlkjihgfedcba",
        "0123456789", "9876543210", "qwertyuiop", "asdfghjkl", "zxcvbnm",
    ]

    def analyze(emp_id: str, name: str, email: str, pwd: str) -> CheckResult:
        issues: List[str] = []
        recs: List[str] = []
        score = 0
        length = len(pwd)

        if length >= 16:
            score += 25
        elif length >= 12:
            score += 20
        elif length >= 8:
            score += 15
        else:
            score += max(0, length * 2)
            issues.append(f"Too short ({length} chars)")
            recs.append(f"Use at least {min_length} characters")

        has_upper = bool(re.search(r"[A-Z]", pwd))
        has_lower = bool(re.search(r"[a-z]", pwd))
        has_digit = bool(re.search(r"\d", pwd))
        has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]", pwd))

        checks = [
            (has_upper, "No uppercase letters", "Add uppercase letters"),
            (has_lower, "No lowercase letters", "Add lowercase letters"),
            (has_digit, "No digits", "Add digits"),
            (has_special, "No special characters", "Add special characters (!@#$%)"),
        ]
        for flag, label, tip in checks:
            if flag:
                score += 15 if label != "No special characters" else 20
            else:
                issues.append(label)
                recs.append(tip)

        has_common = pwd.lower() in COMMON
        if has_common:
            score = 0
            issues.append("Common password!")
            recs.append("Choose a unique password")

        has_repeats = bool(re.search(r"(.)\1{2,}", pwd))
        if has_repeats:
            score -= 10
            issues.append("Repeating characters (aaa, 111)")
            recs.append("Avoid repetitions")

        has_sequence = any(
            seq[i : i + 3] in pwd.lower()
            for seq in SEQUENCES
            for i in range(len(seq) - 2)
        )
        if has_sequence:
            score -= 10
            issues.append("Simple sequences (123, abc)")
            recs.append("Avoid sequences")

        if length > 20:
            score += 5
        score = max(0, min(100, score))

        if score >= 80:
            strength = "Excellent"
        elif score >= 60:
            strength = "Good"
        elif score >= 40:
            strength = "Medium"
        elif score >= 20:
            strength = "Weak"
        else:
            strength = "Critical"

        if not issues:
            recs.append("Password is secure!")

        return CheckResult(
            emp_id, name, email, "*" * length, length,
            has_upper, has_lower, has_digit, has_special,
            has_common, has_repeats, has_sequence, score,
            strength, issues, recs,
        )

    def generate_reports(results: List[CheckResult]) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")

        # CSV
        csv_path = output_dir / f"report_{ts}.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([
                "ID", "Name", "Email", "Length", "A-Z", "a-z", "0-9", "!@#",
                "Common", "Repeats", "Sequence", "Score", "Grade", "Issues",
            ])
            for r in results:
                w.writerow([
                    r.employee_id, r.name, r.email, r.length,
                    "Yes" if r.has_upper else "No",
                    "Yes" if r.has_lower else "No",
                    "Yes" if r.has_digit else "No",
                    "Yes" if r.has_special else "No",
                    "Yes" if r.has_common else "No",
                    "Yes" if r.has_repeats else "No",
                    "Yes" if r.has_sequence else "No",
                    r.score, r.strength, "; ".join(r.issues) if r.issues else "None",
                ])
        logging.info("[OK] CSV report: %s", csv_path)

        # JSON
        json_path = output_dir / f"report_{ts}.json"
        data = {
            "generated": datetime.now().isoformat(),
            "total": len(results),
            "average": round(sum(r.score for r in results) / len(results), 1),
            "weak": sum(1 for r in results if r.score < min_score),
            "checks": [asdict(r) for r in results],
        }
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info("[OK] JSON report: %s", json_path)

        # HTML
        colors = {
            "Excellent": "#27ae60", "Good": "#2ecc71", "Medium": "#f39c12",
            "Weak": "#e67e22", "Critical": "#e74c3c",
        }
        rows = []
        for r in results:
            c = colors.get(r.strength, "#95a5a6")
            iss = "<br>".join(f"- {i}" for i in r.issues) if r.issues else '<span style="color:#27ae60">OK</span>'
            rec = "<br>".join(f"-> {x}" for x in r.recommendations)
            rows.append(
                f"<tr><td>{r.employee_id}</td><td>{r.name}</td><td>{r.email}</td>"
                f"<td>{r.length}</td><td>{'Yes' if r.has_upper else 'No'}</td>"
                f"<td>{'Yes' if r.has_lower else 'No'}</td>"
                f"<td>{'Yes' if r.has_digit else 'No'}</td>"
                f"<td>{'Yes' if r.has_special else 'No'}</td>"
                f'<td><span style="color:{c};font-weight:bold">{r.score}</span></td>'
                f'<td style="color:{c};font-weight:bold">{r.strength}</td>'
                f"<td>{iss}</td><td>{rec}</td></tr>"
            )

        html = (
            "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><title>Password Report</title>"
            "<style>"
            "body{font-family:Arial,sans-serif;background:#f5f7fa;padding:20px}"
            "table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}"
            "th{background:#1a252f;color:#fff;padding:12px;text-align:left}"
            "td{padding:12px;border-bottom:1px solid #ecf0f1;font-size:0.9em}"
            "tr:hover{background:#f8f9fa}"
            "</style></head><body>"
            "<h1>Password Security Report</h1>"
            f"<p>Generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>"
            "<table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Length</th>"
            "<th>A-Z</th><th>a-z</th><th>0-9</th><th>!@#</th><th>Score</th><th>Grade</th>"
            "<th>Issues</th><th>Tips</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></body></html>"
        )
        html_path = output_dir / f"report_{ts}.html"
        with html_path.open("w", encoding="utf-8") as f:
            f.write(html)
        logging.info("[OK] HTML report: %s", html_path)

    # Create sample CSV if missing
    if not input_csv.exists():
        input_csv.write_text(
            "employee_id,name,email,password\n"
            "EMP001,Ivanov Ivan,ivanov@company.ru,Password123!\n"
            "EMP002,Petrova Anna,petrova@company.ru,12345678\n"
            "EMP003,Sidorov Oleg,sidorov@company.ru,MyS3cur3P@ss!\n"
            "EMP004,Kozlova Maria,kozlova@company.ru,qwerty\n"
            "EMP005,Novikov Dmitry,novikov@company.ru,Aa1!Bb2@Cc3#\n"
            "EMP006,Morozova Elena,morozova@company.ru,password\n"
            "EMP007,Volkov Alexey,volkov@company.ru,Tr0ub4dor&3\n"
            "EMP008,Lebedeva Olga,lebedeva@company.ru,11111111\n",
            encoding="utf-8-sig",
        )
        logging.info("Sample CSV created: %s. Edit it and re-run.", input_csv)
        return

    employees = []
    with input_csv.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            employees.append(row)

    logging.info("Loaded employees: %d", len(employees))
    results = []
    for emp in employees:
        r = analyze(
            emp.get("employee_id", "N/A"),
            emp.get("name", "N/A"),
            emp.get("email", "N/A"),
            emp.get("password", ""),
        )
        results.append(r)
        status = "OK" if r.score >= min_score else "FAIL"
        logging.info("%s %s: %s (%d/100)", status, r.name, r.strength, r.score)

    logging.info("Generating reports...")
    generate_reports(results)
    weak = sum(1 for r in results if r.score < min_score)
    logging.info("Weak passwords: %d of %d", weak, len(results))


# ==============================================================================
# MODULE 4: EMAIL REMINDERS
# ==============================================================================
def run_email_remind(args: argparse.Namespace) -> None:
    """Send templated email reminders from CSV."""
    smtp_server = args.smtp_server or os.getenv("SMTP_SERVER") or _cfg("email.smtp_server", "smtp.gmail.com")
    smtp_port = args.smtp_port or int(os.getenv("SMTP_PORT") or _cfg("email.smtp_port", 587))
    smtp_user = args.smtp_user or os.getenv("SMTP_USER") or _cfg("email.smtp_user")
    smtp_password = args.smtp_password or os.getenv("SMTP_PASSWORD") or _cfg("email.smtp_password")
    from_name = args.from_name or os.getenv("FROM_NAME") or _cfg("email.from_name", "Reminder System")
    input_csv = Path(args.input or _cfg("email.input_csv", "reminders.csv"))
    log_file = Path(args.log or _cfg("email.log_file", "email_log.txt"))
    use_ssl = args.ssl or _cfg("email.use_ssl", False)

    if not smtp_user or not smtp_password:
        _die(
            "SMTP credentials not configured.\n"
            "Add to .env:\n"
            "  SMTP_USER=your-email@gmail.com\n"
            "  SMTP_PASSWORD=your-app-password\n"
            "Gmail App-Password: https://myaccount.google.com/apppasswords"
        )

    TEMPLATES = {
        "parent": {
            "subject": "Reminder: {event}",
            "body": (
                "Hello {name},\n\n"
                "Reminder: {event}\nDate: {date}\n\n{message}\n\n"
                "Best regards,\n{from_name}"
            ),
            "html": (
                "<html><body style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;\">"
                "<div style=\"background:#4a90d9;color:#fff;padding:20px;border-radius:8px 8px 0 0\"><h2>Reminder</h2></div>"
                "<div style=\"background:#f9f9f9;padding:20px;border:1px solid #e0e0f0\">"
                "<p>Hello <strong>{name}</strong>!</p>"
                "<p>Reminder:</p>"
                "<div style=\"background:#fff;padding:15px;border-radius:6px;margin:15px 0;border-left:4px solid #4a90d9\">"
                "<h3>{event}</h3><p><strong>Date:</strong> {date}</p></div>"
                "<p>{message}</p><hr>"
                "<p style=\"color:#999;font-size:0.9em\">Best regards,<br>{from_name}</p>"
                "</div></body></html>"
            ),
        },
        "employee": {
            "subject": "Reminder: {event}",
            "body": (
                "Hello {name},\n\n"
                "Reminder: {event}\nDate: {date}\n\n{message}\n\n"
                "Please prepare in time.\n\nBest regards,\n{from_name}"
            ),
            "html": (
                "<html><body style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;\">"
                "<div style=\"background:#e67e22;color:#fff;padding:20px;border-radius:8px 8px 0 0\"><h2>Employee Reminder</h2></div>"
                "<div style=\"background:#f9f9f9;padding:20px;border:1px solid #e0e0f0\">"
                "<p>Hello <strong>{name}</strong>!</p>"
                "<p>Reminder:</p>"
                "<div style=\"background:#fff;padding:15px;border-radius:6px;margin:15px 0;border-left:4px solid #e67e22\">"
                "<h3>{event}</h3><p><strong>Date:</strong> {date}</p></div>"
                "<p>{message}</p><hr>"
                "<p style=\"color:#999;font-size:0.9em\">Please prepare in time.</p>"
                "<p style=\"color:#999;font-size:0.9em\">Best regards,<br>{from_name}</p>"
                "</div></body></html>"
            ),
        },
    }

    class Sender:
        def __init__(self) -> None:
            self.server: Optional[smtplib.SMTP] = None
            self.sent = 0
            self.err = 0

        def connect(self) -> None:
            logging.info("Connecting to %s:%d...", smtp_server, smtp_port)
            if use_ssl:
                self.server = smtplib.SMTP_SSL(smtp_server, smtp_port, context=ssl.create_default_context())
            else:
                self.server = smtplib.SMTP(smtp_server, smtp_port)
                self.server.starttls(context=ssl.create_default_context())
            self.server.login(smtp_user, smtp_password)
            logging.info("Connected.")

        def disconnect(self) -> None:
            if self.server:
                self.server.quit()
                logging.info("Connection closed.")

        def send(self, to: str, subject: str, text: str, html: str, name: str = "") -> None:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{smtp_user}>"
            msg["To"] = to
            msg.attach(MIMEText(text, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
            try:
                self.server.sendmail(smtp_user, [to], msg.as_string())
                self.sent += 1
                logging.info("[OK] %s <%s>", name, to)
            except Exception as exc:
                self.err += 1
                logging.error("[ERR] %s <%s>: %s", name, to, exc)

        def save_log(self) -> None:
            with log_file.open("w", encoding="utf-8") as f:
                f.write(f"Email Log: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Sent: {self.sent}, Errors: {self.err}\n")
            logging.info("Log saved: %s", log_file)

    if not input_csv.exists():
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
        input_csv.write_text(
            "name,email,type,event,date,message\n"
            f"Maria Ivanova,parent1@example.com,parent,Parent Meeting,{tomorrow},Please bring the diary.\n"
            f"Sergey Petrov,parent2@example.com,parent,Extra courses payment,{next_week},Amount: 3500 EUR.\n"
            f"Anna Sidorova,employee1@company.ru,employee,Project Alpha Meeting,{tomorrow},Prepare progress report.\n"
            f"Dmitry Kozlov,employee2@company.ru,employee,Quarterly Report Deadline,{next_week},Must be approved by 17:00.\n",
            encoding="utf-8-sig",
        )
        logging.info("Sample CSV created: %s. Edit it and re-run.", input_csv)
        return

    reminders = []
    with input_csv.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            reminders.append(row)

    logging.info("Loaded reminders: %d", len(reminders))
    sender = Sender()
    sender.connect()

    for i, r in enumerate(reminders, 1):
        rtype = r.get("type", "parent").strip().lower()
        name = r.get("name", "").strip()
        email = r.get("email", "").strip()
        event = r.get("event", "").strip()
        date = r.get("date", "").strip()
        message = r.get("message", "").strip()

        if not email or not event:
            logging.warning("[SKIP] Entry %d: missing data", i)
            continue

        tmpl = TEMPLATES.get(rtype, TEMPLATES["parent"])
        subject = tmpl["subject"].format(event=event)
        body = tmpl["body"].format(name=name, event=event, date=date, message=message, from_name=from_name)
        html = tmpl["html"].format(name=name, event=event, date=date, message=message, from_name=from_name)

        logging.info("[%d/%d] Sending: %s", i, len(reminders), subject)
        sender.send(email, subject, body, html, name)
        if i < len(reminders):
            time.sleep(1)

    sender.disconnect()
    sender.save_log()
    logging.info("Done. Sent: %d, Errors: %d", sender.sent, sender.err)


# ==============================================================================
# CLI
# ==============================================================================
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Python IT Automation Suite - Fachinformatiker Praktikum",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Google Drive backup
  python automation_suite.py backup-gdrive --folders ./docs ./projects

  # Dropbox backup
  python automation_suite.py backup-dropbox --folders ./docs

  # Password audit
  python automation_suite.py password-check --input employees.csv --output reports/

  # Email reminders
  python automation_suite.py email-remind --input reminders.csv
        """,
    )
    sub = parser.add_subparsers(dest="module", required=True)

    # backup-gdrive
    p_gd = sub.add_parser("backup-gdrive", help="Backup to Google Drive")
    p_gd.add_argument("--folders", nargs="+", help="Local folders to backup")
    p_gd.add_argument("--exclude", nargs="+", help="Patterns to exclude")
    p_gd.add_argument("--name", help="Backup folder name prefix")
    p_gd.add_argument("--credentials", help="Path to credentials.json")
    p_gd.add_argument("--token", help="Path to token.json")
    p_gd.add_argument("--headless", action="store_true", help="Use console OAuth flow (for servers)")

    # backup-dropbox
    p_db = sub.add_parser("backup-dropbox", help="Backup to Dropbox")
    p_db.add_argument("--folders", nargs="+", help="Local folders to backup")
    p_db.add_argument("--exclude", nargs="+", help="Patterns to exclude")
    p_db.add_argument("--name", help="Backup folder name prefix")
    p_db.add_argument("--token", help="Dropbox access token (or env DROPBOX_TOKEN)")
    p_db.add_argument("--path", default="/Backups", help="Dropbox base path")

    # password-check
    p_pw = sub.add_parser("password-check", help="Password strength audit")
    p_pw.add_argument("--input", help="Input CSV path")
    p_pw.add_argument("--output", help="Output directory")
    p_pw.add_argument("--min-length", type=int, help="Minimum length")
    p_pw.add_argument("--min-score", type=int, help="Minimum score to pass")

    # email-remind
    p_em = sub.add_parser("email-remind", help="Send email reminders")
    p_em.add_argument("--input", help="Reminders CSV path")
    p_em.add_argument("--smtp-server", help="SMTP server")
    p_em.add_argument("--smtp-port", type=int, help="SMTP port")
    p_em.add_argument("--smtp-user", help="SMTP username")
    p_em.add_argument("--smtp-password", help="SMTP password")
    p_em.add_argument("--from-name", help="Sender display name")
    p_em.add_argument("--log", help="Log file path")
    p_em.add_argument("--ssl", action="store_true", help="Use SMTP_SSL instead of STARTTLS")

    return parser


def main() -> None:
    _setup_logging()
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.module == "backup-gdrive":
            run_backup_gdrive(args)
        elif args.module == "backup-dropbox":
            run_backup_dropbox(args)
        elif args.module == "password-check":
            run_password_check(args)
        elif args.module == "email-remind":
            run_email_remind(args)
    except KeyboardInterrupt:
        logging.warning("Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
