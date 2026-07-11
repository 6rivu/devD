import os, smtplib
from email.mime.text import MIMEText

def load_env_file(path=".env"):
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)
    except FileNotFoundError:
        pass

load_env_file(".env")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USERNAME")
SMTP_PASS   = os.getenv("SMTP_PASSWORD")
SMTP_FROM   = os.getenv("SMTP_FROM", SMTP_USER)
TO_EMAIL    = SMTP_USER  # change if needed

msg = MIMEText("This is a CvolvePro SMTP test.")
msg["Subject"] = "SMTP Test"
msg["From"] = SMTP_FROM
msg["To"] = TO_EMAIL

try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [TO_EMAIL], msg.as_string())
    print("✅ Test email sent. Check your inbox.")
except Exception as e:
    print("❌ Failed to send:", repr(e))

