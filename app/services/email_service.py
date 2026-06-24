"""
Email service for period-wise attendance notifications.

Architecture:
  - Called from cv_worker finalize path via asyncio.create_task()
  - NEVER blocks the CV worker — fire and forget
  - Uses aiosmtplib for async (non-blocking) SMTP
  - Reads EmailSettings from DB (one row per branch)
  - Decrypts SMTP password at send time using Fernet
  - Writes result (DELIVERED/FAILED) to the notifications table

NOTE: Adapted to this project's schema:
  - Parent email/name come from the `parents` table directly (par.email / par.full_name)
  - The `notifications` table has no recipient_email/message columns — the email
    address and subject are stored in the `payload` JSONB column instead.
  - Period times come from `attendance_windows` (start_time / end_time).
"""

import json
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.models.email_settings import EmailSettings

log = logging.getLogger(__name__)

# Jinja2 template environment
_template_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent.parent / "templates" / "email")),
    autoescape=select_autoescape(["html", "xml"]),
)


# ── Global SMTP fallback (env-based) ──────────────────────────────────────────

class _EnvEmailConfig:
    """Drop-in stand-in for EmailSettings, built from environment variables.

    Carries the SMTP password in plaintext (``_plain_password``) so the sender
    skips Fernet decryption for the env fallback.
    """
    def __init__(self) -> None:
        from app.core.config import settings as s
        self.sender_name = s.SMTP_SENDER_NAME or s.SCHOOL_NAME
        self.sender_email = s.SMTP_SENDER_EMAIL or s.SMTP_USER or s.EMAIL_FROM
        self.smtp_host = s.SMTP_HOST
        self.smtp_port = s.SMTP_PORT or 587
        self.smtp_user = s.SMTP_USER
        self.smtp_password = s.SMTP_PASSWORD
        self._plain_password = s.SMTP_PASSWORD
        self.use_tls = True
        self.is_active = True


def _env_config_available() -> bool:
    from app.core.config import settings as s
    return bool(s.SMTP_HOST and s.SMTP_USER and s.SMTP_PASSWORD)


# ── Public: load settings ─────────────────────────────────────────────────────

async def get_email_settings(
    branch_id: str,
    db: AsyncSession,
):
    """Return the active email config for a branch.

    Prefers a per-branch ``email_settings`` row; falls back to a global SMTP
    config from environment variables when no branch row is configured.
    """
    cfg = None
    if branch_id:
        result = await db.execute(
            select(EmailSettings).where(
                EmailSettings.branch_id == branch_id,
                EmailSettings.is_active == True,  # noqa: E712
            )
        )
        cfg = result.scalar_one_or_none()

    if cfg is None and _env_config_available():
        return _EnvEmailConfig()
    return cfg


# ── Public: send one email ────────────────────────────────────────────────────

async def send_single_email(
    to_email: str,
    subject: str,
    html_body: str,
    cfg: EmailSettings,
) -> bool:
    """
    Send one email via aiosmtplib.
    Returns True on success, False on any failure.
    Logs the error but does not raise — caller handles failure gracefully.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        # Env-fallback configs carry the password in plaintext; DB rows are Fernet-encrypted.
        plain = getattr(cfg, "_plain_password", None)
        if plain is not None:
            smtp_password = plain
        else:
            smtp_password = decrypt(cfg.smtp_password) if cfg.smtp_password else ""

        await aiosmtplib.send(
            msg,
            hostname=cfg.smtp_host or "smtp.gmail.com",
            port=cfg.smtp_port or 587,
            username=cfg.smtp_user,
            password=smtp_password,
            use_tls=cfg.smtp_port == 465,    # SSL (port 465)
            start_tls=cfg.smtp_port != 465,  # STARTTLS (port 587 or 25)
            timeout=15,                      # seconds — don't hang forever
        )
        log.info("[email] sent to %s", to_email)
        return True

    except aiosmtplib.SMTPAuthenticationError:
        log.error("[email] auth failed for %s — check App Password", to_email)
        return False
    except aiosmtplib.SMTPConnectError as e:
        log.error("[email] connect failed (%s:%s): %s", cfg.smtp_host, cfg.smtp_port, e)
        return False
    except Exception as e:
        log.error("[email] unexpected error to %s: %s", to_email, e)
        return False


# ── Public: send test email ───────────────────────────────────────────────────

async def send_test_email(
    to_email: str,
    cfg: EmailSettings,
) -> tuple[bool, str]:
    """
    Send a test email to verify SMTP credentials.
    Returns (success: bool, message: str).
    Called from POST /settings/email/test endpoint.
    """
    html = """
    <div style="font-family:Arial,sans-serif;padding:24px;max-width:480px;">
      <h2 style="color:#2563EB;">AMS Email Setup Verified</h2>
      <p style="color:#374151;">
        Your email settings are configured correctly.
        Attendance alerts will be sent to parents from this address.
      </p>
      <p style="color:#64748b;font-size:12px;">
        This is a test message from the Attendance Management System.
      </p>
    </div>
    """
    ok = await send_single_email(
        to_email=to_email,
        subject="[AMS] Email Setup Verified — Test Message",
        html_body=html,
        cfg=cfg,
    )
    if ok:
        return True, "Test email sent successfully"
    return False, "Failed to send — check SMTP credentials and App Password"


# ── Public: parent welcome / credentials email ────────────────────────────────

async def send_account_created_emails(
    branch_id: str,
    recipients: list[dict],
    db: AsyncSession,
) -> None:
    """
    Email each newly created parent "Your account has been created" with their
    login credentials. Fire-and-forget — owns its own DB session.

    Each recipient dict: {parent_id, email, name, password, relationship}.
    Exits silently if the branch has no active email settings.
    """
    try:
        cfg = await get_email_settings(str(branch_id), db)
        if not cfg:
            log.debug("[email] No active email settings for branch=%s — skipping welcome", branch_id)
            return

        from app.core.config import settings as app_settings
        portal_link = getattr(app_settings, "PARENT_PORTAL_BASE_URL", None)
        template = _template_env.get_template("account_created.html")
        sent = 0

        for r in recipients:
            to_email = r.get("email")
            if not to_email:
                continue

            html = template.render(
                parent_name=r.get("name") or "Parent",
                login_email=to_email,
                password=r.get("password") or "",
                school_name=cfg.sender_name or "Your School",
                portal_link=portal_link,
            )

            ok = await send_single_email(
                to_email=to_email,
                subject="Your account has been created",
                html_body=html,
                cfg=cfg,
            )

            payload = {"recipient_email": to_email, "subject": "Your account has been created"}
            await db.execute(
                text("""
                    INSERT INTO notifications (
                        id, branch_id, parent_id, trigger_type, channel,
                        status, sent_at, failure_reason, payload, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :branch_id, :parent_id, 'BULK', 'EMAIL',
                        :status, now(), :failure_reason, CAST(:payload AS JSONB), now(), now()
                    )
                """),
                {
                    "branch_id": str(branch_id),
                    "parent_id": str(r["parent_id"]) if r.get("parent_id") else None,
                    "status": "DELIVERED" if ok else "FAILED",
                    "failure_reason": None if ok else "SMTP send failed",
                    "payload": json.dumps(payload),
                },
            )
            if ok:
                sent += 1

        await db.commit()
        log.info("[email] Welcome: %d/%d account emails sent for branch=%s",
                 sent, len(recipients), branch_id)

    except Exception:
        log.exception("[email] send_account_created_emails failed for branch=%s", branch_id)
        try:
            await db.rollback()
        except Exception:
            pass
    finally:
        await db.close()


# ── Public: main task (called from CV worker) ─────────────────────────────────

async def send_period_attendance_emails(
    window_id: str,
    db: AsyncSession,
) -> None:
    """
    Sends one email per parent whose child was ABSENT or LATE in this window.
    Includes subject name, teacher, period time, and date.

    IMPORTANT: Always called via asyncio.create_task() from the CV worker —
    it must NEVER be awaited directly, to avoid blocking the next period's
    attendance window. Owns its own DB session (closed on exit).

    Flow:
      1. Resolve the branch for this window
      2. Load active email settings — if none, exit silently
      3. Query absent/late students + parent emails for this window
      4. Render and send the HTML email for each
      5. Record DELIVERED/FAILED in the notifications table
    """
    try:
        # 1. Resolve branch from the window's section -> class
        branch_id = (
            await db.execute(
                text("""
                    SELECT c.branch_id
                    FROM attendance_windows aw
                    JOIN sections sec ON sec.id = aw.section_id
                    JOIN classes  c   ON c.id   = sec.class_id
                    WHERE aw.id = :window_id
                """),
                {"window_id": window_id},
            )
        ).scalar_one_or_none()

        if not branch_id:
            log.debug("[email] No branch found for window=%s — skipping", window_id)
            return

        # 2. Load active settings for the branch
        cfg = await get_email_settings(str(branch_id), db)
        if not cfg:
            log.debug("[email] No active email settings for branch=%s — skipping", branch_id)
            return

        # 3. Single query — everything needed for absent/late parents
        result = await db.execute(
            text("""
                SELECT
                    s.id                                  AS student_id,
                    par.id                                AS parent_id,
                    a.status                              AS status,
                    a.attendance_date::text               AS attendance_date,
                    s.first_name || ' ' || s.last_name    AS student_name,
                    c.grade                               AS grade,
                    sec.name                              AS section_name,
                    COALESCE(sub.name, 'Period')          AS subject_name,
                    COALESCE(u_t.name, '—')               AS teacher_name,
                    TO_CHAR(aw.start_time, 'HH12:MI AM')  AS start_time,
                    TO_CHAR(aw.end_time,   'HH12:MI AM')  AS end_time,
                    COALESCE(par.email, u_p.email)        AS parent_email,
                    par.full_name                         AS parent_name
                FROM attendance a
                JOIN students           s   ON s.id   = a.student_id
                JOIN sections           sec ON sec.id = a.section_id
                JOIN classes            c   ON c.id   = sec.class_id
                JOIN attendance_windows aw  ON aw.id  = a.attendance_window_id
                LEFT JOIN timetable_entries te  ON te.id  = aw.timetable_entry_id
                LEFT JOIN subjects          sub ON sub.id = te.subject_id
                LEFT JOIN teacher_profiles  tp  ON tp.id  = te.teacher_profile_id
                LEFT JOIN users             u_t ON u_t.id = tp.user_id
                JOIN student_parents        sp  ON sp.student_id = s.id
                JOIN parents                par ON par.id = sp.parent_id
                LEFT JOIN users             u_p ON u_p.id = par.user_id
                WHERE a.attendance_window_id = :window_id
                  AND a.status IN ('ABSENT', 'LATE')
                  AND COALESCE(par.email, u_p.email) IS NOT NULL
                  AND COALESCE(par.email, u_p.email) != ''
                ORDER BY s.first_name
            """),
            {"window_id": window_id},
        )

        rows = result.mappings().fetchall()
        if not rows:
            log.debug("[email] No absent/late students with parent emails for window=%s", window_id)
            return

        log.info("[email] Sending %d period email(s) for window=%s", len(rows), window_id)

        template = _template_env.get_template("period_attendance.html")
        sent = 0

        for row in rows:
            html = template.render(
                parent_name=row["parent_name"],
                student_name=row["student_name"],
                status=row["status"],
                subject_name=row["subject_name"],
                teacher_name=row["teacher_name"],
                section=f'{row["grade"]} — Section {row["section_name"]}',
                period_time=f'{row["start_time"]} – {row["end_time"]}',
                date=row["attendance_date"],
                school_name=cfg.sender_name or "Your School",
            )

            email_subject = (
                f"[Attendance] {row['student_name']} marked {row['status'].capitalize()} "
                f"— {row['subject_name']} ({row['start_time']} – {row['end_time']})"
            )

            ok = await send_single_email(
                to_email=row["parent_email"],
                subject=email_subject,
                html_body=html,
                cfg=cfg,
            )

            # Record in notifications table (schema-accurate: payload JSONB)
            payload = {
                "recipient_email": row["parent_email"],
                "subject": email_subject,
                "window_id": str(window_id),
                "attendance_date": row["attendance_date"],
            }
            await db.execute(
                text("""
                    INSERT INTO notifications (
                        id, branch_id, student_id, parent_id,
                        trigger_type, channel, status, sent_at,
                        failure_reason, payload, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :branch_id, :student_id, :parent_id,
                        :trigger, 'EMAIL', :status, now(),
                        :failure_reason, CAST(:payload AS JSONB), now(), now()
                    )
                """),
                {
                    "branch_id": str(branch_id),
                    "student_id": str(row["student_id"]),
                    "parent_id": str(row["parent_id"]),
                    "trigger": "ABSENT" if row["status"] == "ABSENT" else "LATE",
                    "status": "DELIVERED" if ok else "FAILED",
                    "failure_reason": None if ok else "SMTP send failed",
                    "payload": json.dumps(payload),
                },
            )

            if ok:
                sent += 1

        await db.commit()
        log.info("[email] Done: %d/%d emails sent for window=%s", sent, len(rows), window_id)

    except Exception:
        log.exception("[email] send_period_attendance_emails failed for window=%s", window_id)
        try:
            await db.rollback()
        except Exception:
            pass
    finally:
        await db.close()
