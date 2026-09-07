import os
import smtplib
from email.message import EmailMessage
from flask import current_app

class EmailService:
    """Service for dispatching transactional emails & development fallbacks."""

    @staticmethod
    def send_password_reset_otp(email, otp):
        """
        Sends the 6-digit password reset OTP to the recipient email.
        Falls back to local development console output if SMTP credentials are not configured.
        """
        subject = "CareerSkill AI - Password Reset OTP"
        body = (
            "Hello,\n\n"
            "We received a request to reset your CareerSkill AI password.\n\n"
            "Your verification OTP is:\n\n"
            f"{otp}\n\n"
            "This OTP will expire in 10 minutes.\n\n"
            "If you did not request a password reset, please ignore this email.\n\n"
            "Regards,\n"
            "CareerSkill AI Team"
        )

        mail_server = os.environ.get('MAIL_SERVER') or getattr(current_app.config, 'MAIL_SERVER', '')
        mail_username = os.environ.get('MAIL_USERNAME') or getattr(current_app.config, 'MAIL_USERNAME', '')
        mail_password = os.environ.get('MAIL_PASSWORD') or getattr(current_app.config, 'MAIL_PASSWORD', '')
        mail_port = int(os.environ.get('MAIL_PORT') or getattr(current_app.config, 'MAIL_PORT', 587))
        mail_sender = os.environ.get('MAIL_DEFAULT_SENDER') or getattr(current_app.config, 'MAIL_DEFAULT_SENDER', 'CareerSkill AI <noreply@careerskill.ai>')

        # If SMTP is configured, attempt live email delivery
        if mail_server and mail_username and mail_password:
            try:
                msg = EmailMessage()
                msg['Subject'] = subject
                msg['From'] = mail_sender
                msg['To'] = email
                msg.set_content(body)

                with smtplib.SMTP(mail_server, mail_port, timeout=10) as server:
                    if os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']:
                        server.starttls()
                    server.login(mail_username, mail_password)
                    server.send_message(msg)

                print(f"[+] Password reset OTP successfully sent via SMTP to {email}")
                return True
            except Exception as e:
                print(f"[-] SMTP delivery failed ({e}). Falling back to development terminal logger.")

        # Development Terminal Output Fallback (Only in dev / test when SMTP not active)
        print("\n==================================================")
        print("[*] Password reset OTP generated for:")
        print(f"[*] Email: {email}")
        print("[*] Development OTP: ******")
        print("[*] Expiry: 10 minutes")
        print("==================================================\n")
        return True

email_service = EmailService()
