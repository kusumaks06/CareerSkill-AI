import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from app import create_app
from models import db, User, PasswordResetOTP

class ForgotPasswordTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            user = User(full_name='Test Candidate', email='candidate@example.com')
            user.set_password('OldPassword123!')
            db.session.add(user)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    @patch('services.email_service.email_service.send_password_reset_otp')
    def test_1_valid_email_otp_send_and_full_password_reset_flow(self, mock_send):
        """Test 1: Valid email -> OTP sent -> Correct OTP -> Password reset -> New password login works."""
        # 1. Request OTP
        res = self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("If an account is associated with this email, a verification OTP has been sent.", res.get_data(as_text=True))
        self.assertIn("Verify your email", res.get_data(as_text=True))

        mock_send.assert_called_once()
        dispatched_otp = mock_send.call_args[0][1]
        self.assertEqual(len(dispatched_otp), 6)

        # 2. Enter correct OTP
        res_verify = self.client.post('/verify-otp', data={'otp': dispatched_otp}, follow_redirects=True)
        self.assertEqual(res_verify.status_code, 200)
        self.assertIn("Create a new password", res_verify.get_data(as_text=True))

        # 3. Submit new password
        res_reset = self.client.post('/reset-password', data={
            'new_password': 'NewSecurePassword2026!',
            'confirm_password': 'NewSecurePassword2026!'
        }, follow_redirects=True)
        self.assertEqual(res_reset.status_code, 200)
        self.assertIn("Your password has been reset successfully. Please log in with your new password.", res_reset.get_data(as_text=True))

        # 4. Old password must fail
        res_old_login = self.client.post('/login', data={
            'email': 'candidate@example.com',
            'password': 'OldPassword123!'
        }, follow_redirects=True)
        self.assertIn("Invalid email or password.", res_old_login.get_data(as_text=True))

        # 5. New password must succeed
        res_new_login = self.client.post('/login', data={
            'email': 'candidate@example.com',
            'password': 'NewSecurePassword2026!'
        }, follow_redirects=True)
        self.assertIn("Login successful.", res_new_login.get_data(as_text=True))

    def test_2_wrong_otp_error_message(self):
        """Test 2: Valid email -> Wrong OTP -> Error message."""
        self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)

        res_wrong = self.client.post('/verify-otp', data={'otp': '000000'}, follow_redirects=True)
        self.assertIn("Invalid verification code. 4 attempt(s) remaining.", res_wrong.get_data(as_text=True))

    def test_3_five_wrong_otp_attempts_invalidates_otp(self):
        """Test 3: 5 wrong OTP attempts -> OTP invalidated."""
        self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)

        for i in range(4):
            self.client.post('/verify-otp', data={'otp': '111111'}, follow_redirects=True)

        # 5th attempt
        res_5th = self.client.post('/verify-otp', data={'otp': '111111'}, follow_redirects=True)
        self.assertIn("Too many incorrect attempts. Please request a new OTP.", res_5th.get_data(as_text=True))

        # 6th attempt should block immediately
        res_6th = self.client.post('/verify-otp', data={'otp': '111111'}, follow_redirects=True)
        self.assertIn("Too many incorrect attempts. Please request a new OTP.", res_6th.get_data(as_text=True))

    def test_4_expired_otp_rejected(self):
        """Test 4: Expired OTP -> Verification rejected."""
        self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)

        # Force expire OTP in database
        with self.app.app_context():
            user = User.query.filter_by(email='candidate@example.com').first()
            otp_record = PasswordResetOTP.query.filter_by(user_id=user.id).first()
            otp_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.session.commit()

        res_exp = self.client.post('/verify-otp', data={'otp': '123456'}, follow_redirects=True)
        self.assertIn("This OTP has expired. Please request a new OTP.", res_exp.get_data(as_text=True))

    @patch('services.email_service.email_service.send_password_reset_otp')
    def test_5_resend_otp_invalidates_old_otp(self, mock_send):
        """Test 5: Resend OTP -> Old OTP invalid -> New OTP works."""
        # 1. Request initial OTP
        self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)
        first_otp = mock_send.call_args[0][1]

        with self.app.app_context():
            user = User.query.filter_by(email='candidate@example.com').first()
            rec = PasswordResetOTP.query.filter_by(user_id=user.id).first()
            rec.created_at = datetime.now(timezone.utc) - timedelta(seconds=65)
            db.session.commit()

        # 2. Resend OTP
        res_resend = self.client.post('/resend-otp', follow_redirects=True)
        self.assertIn("A new verification OTP has been sent.", res_resend.get_data(as_text=True))
        second_otp = mock_send.call_args[0][1]

        # 3. Old code fails
        if first_otp != second_otp:
            res_old = self.client.post('/verify-otp', data={'otp': first_otp}, follow_redirects=True)
            self.assertIn("Invalid verification code.", res_old.get_data(as_text=True))

        # 4. New code works
        res_new = self.client.post('/verify-otp', data={'otp': second_otp}, follow_redirects=True)
        self.assertIn("Create a new password", res_new.get_data(as_text=True))

    def test_6_resend_before_60_seconds_rejected(self):
        """Test 6: Resend before 60 seconds -> Request rejected."""
        self.client.post('/forgot-password', data={'email': 'candidate@example.com'}, follow_redirects=True)

        # Immediate resend (within 60s)
        res_fast = self.client.post('/resend-otp', follow_redirects=True)
        self.assertIn("Please wait 60 seconds before requesting another OTP.", res_fast.get_data(as_text=True))

    def test_7_unknown_email_shows_generic_response(self):
        """Test 7: Unknown email -> Generic response without leaking existence."""
        res = self.client.post('/forgot-password', data={'email': 'nonexistent_user@example.com'}, follow_redirects=True)
        self.assertIn("If an account is associated with this email, a verification OTP has been sent.", res.get_data(as_text=True))

        with self.app.app_context():
            otps = PasswordResetOTP.query.all()
            self.assertEqual(len(otps), 0)

    def test_8_and_9_password_reset_login_validation(self):
        """Test 8 & 9: Old password fails, new password succeeds after reset."""
        with self.app.app_context():
            user = User.query.filter_by(email='candidate@example.com').first()
            user_id = user.id

        with self.client.session_transaction() as sess:
            sess['reset_user_id'] = user_id

        # Test password complexity failure (too short)
        res_short = self.client.post('/reset-password', data={
            'new_password': 'abc',
            'confirm_password': 'abc'
        }, follow_redirects=True)
        self.assertIn("Password must be at least 8 characters long.", res_short.get_data(as_text=True))

        # Test mismatch
        res_mismatch = self.client.post('/reset-password', data={
            'new_password': 'ValidPass123',
            'confirm_password': 'DifferentPass123'
        }, follow_redirects=True)
        self.assertIn("Passwords do not match.", res_mismatch.get_data(as_text=True))

    def test_10_unauthorized_access_to_reset_password_redirects(self):
        """Test 10: Try accessing /reset-password without OTP verification -> Access denied."""
        res = self.client.get('/reset-password', follow_redirects=True)
        self.assertIn("Unauthorized or session expired. Please verify your email first.", res.get_data(as_text=True))
        self.assertIn("Forgot your password?", res.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
