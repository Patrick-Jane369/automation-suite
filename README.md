# Python IT Automation Suite

> **Author:** Timofey Vishnevskiy  
> **GitHub:** [@Patrick-Jane369](https://github.com/Patrick-Jane369)  
> **Created:** 2026  
> **Purpose:** Praktikum als Fachinformatiker (Anwendungsentwicklung) in Deutschland  
> **License:** MIT

> **EN:** One file, four tools for IT automation.  
> **DE:** Ein Datei, vier Tools für IT-Automation.  
> **RU:** Один файл, четыре инструмента для IT-автоматизации.
---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/automation-suite.git
cd automation-suite
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your credentials
cp config.yaml config.yaml
# Edit config.yaml if you want to change default paths
```

### 3. Run

```bash
# See all options
python automation_suite.py --help

# Module 1: Google Drive backup
python automation_suite.py backup-gdrive --folders ./docs ./photos

# Module 2: Dropbox backup
python automation_suite.py backup-dropbox --folders ./docs

# Module 3: Password audit (creates sample CSV automatically)
python automation_suite.py password-check --input employees.csv --output reports/

# Module 4: Email reminders (creates sample CSV automatically)
python automation_suite.py email-remind --input reminders.csv
```

---

## Modules

### `backup-gdrive`

Backs up local folders to Google Drive preserving directory structure.

**Prerequisites:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create OAuth 2.0 credentials (Desktop app)
3. Download `credentials.json` to project root
4. Run the script — it will open a browser for authentication (or use `--headless` on servers)

```bash
python automation_suite.py backup-gdrive   --folders ./documents ./projects   --exclude "*.tmp" "*.log" ".git"
```

### `backup-dropbox`

Backs up local folders to Dropbox.

**Prerequisites:**
1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Create app → generate **access token**
3. Add to `.env`:
   ```
   DROPBOX_TOKEN=your_token_here
   ```

```bash
python automation_suite.py backup-dropbox --folders ./documents
```

### `password-check`

Audits password strength from a CSV file and generates **CSV**, **JSON**, and **HTML** reports.

**CSV format:**
```csv
employee_id,name,email,password
EMP001,Ivanov Ivan,ivanov@company.ru,Password123!
```

If `employees.csv` does not exist, the script creates a sample one automatically.

**Scoring:**
- Length, uppercase, lowercase, digits, special chars
- Penalty for common passwords, repetitions, sequences
- 0–100 scale: Excellent (≥80), Good (≥60), Medium (≥40), Weak (≥20), Critical (<20)

### `email-remind`

Sends templated email reminders from a CSV file.

Supports **Gmail**, **Yandex**, **Mail.ru**, or any SMTP server.

**CSV format:**
```csv
name,email,type,event,date,message
Maria Ivanova,parent@example.com,parent,Meeting,01.01.2026,Bring diary
```

Types: `parent` (blue theme) or `employee` (orange theme).

If `reminders.csv` does not exist, the script creates a sample one automatically.

---

## Configuration Priority

1. **CLI arguments** (highest priority)
2. **Environment variables** (from `.env`)
3. **config.yaml** (default values)

---

## Project Structure

```
automation-suite/
├── automation_suite.py   # Main script
├── requirements.txt      # Dependencies
├── config.yaml           # Default settings
├── .env.example          # Template for secrets
├── .gitignore            # Ignores tokens & reports
├── examples/
│   ├── employees.csv.example
│   └── reminders.csv.example
└── tests/
    └── test_password_check.py
```

---

## Security Notes

- **Never commit** `.env`, `token.json`, or `credentials.json` to Git!
- Use [Gmail App Passwords](https://myaccount.google.com/apppasswords) instead of your main password.
- For Dropbox, use a token with limited scope if possible.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Missing dependency: python-dotenv` | Run `pip install -r requirements.txt` |
| Google auth browser does not open | Use `--headless` flag for console flow |
| Gmail blocks login | Enable 2FA and use App Password |
| `DROPBOX_TOKEN not set` | Add token to `.env` file |
| CSV not found | Script auto-creates sample — just edit it |

---

## License

MIT License — feel free to use and modify for your own projects.
