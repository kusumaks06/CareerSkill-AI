import unittest
from app import create_app
from models import db, User, TargetCareer, UserProfile


class TestWelcomeMessageFlow(unittest.TestCase):
    """Test suite for first-time registration vs returning user welcome messages."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_first_time_registration_shows_first_time_welcome_message(self):
        """
        1. Register a brand-new user.
        2. Verify 'Welcome to CareerSkill AI, [name]! 🎉' and
           'Your account has been created successfully. Let's build your career journey.' appear.
        3. Verify 'Welcome back' does NOT appear on initial dashboard access.
        """
        reg_resp = self.client.post('/register', data={
            'full_name': 'Alex Johnson',
            'email': 'alex.j@example.com',
            'password': 'SecurePassword2026!',
            'target_role': 'Data Analyst'
        }, follow_redirects=True)

        self.assertEqual(reg_resp.status_code, 200)
        html = reg_resp.get_data(as_text=True)

        # Verify FIRST-TIME USER message
        self.assertIn("Welcome to CareerSkill AI,", html)
        self.assertIn("Alex Johnson", html)
        self.assertIn("Your account has been created successfully. Let's build your career journey.", html)
        
        # Verify RETURNING USER message does NOT appear
        self.assertNotIn("Welcome back,", html)
        self.assertNotIn("Continue your journey toward", html)

    def test_logout_and_login_again_shows_returning_user_message(self):
        """
        1. Register a brand-new user.
        2. Verify first-time greeting.
        3. Logout.
        4. Login again with same credentials.
        5. Verify 'Welcome back, [name]! 👋' and 'Continue your journey toward [target career].' appear.
        """
        # Step 1: Register
        self.client.post('/register', data={
            'full_name': 'Samantha Reed',
            'email': 'samantha@example.com',
            'password': 'StrongPassword2026!',
            'target_role': 'Machine Learning Engineer'
        }, follow_redirects=True)

        # Step 2: Logout
        logout_resp = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)

        # Step 3: Login again
        login_resp = self.client.post('/login', data={
            'email': 'samantha@example.com',
            'password': 'StrongPassword2026!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        html = login_resp.get_data(as_text=True)

        # Verify RETURNING USER message
        self.assertIn("Welcome back,", html)
        self.assertIn("Samantha Reed", html)
        self.assertIn("Continue your journey toward", html)
        self.assertIn("Machine Learning Engineer", html)

        # Verify FIRST-TIME message does NOT appear
        self.assertNotIn("Welcome to CareerSkill AI,", html)
        self.assertNotIn("Your account has been created successfully.", html)

    def test_dashboard_refresh_marks_first_login_completed(self):
        """
        1. Register a new user and hit dashboard (1st time).
        2. Next GET to /dashboard should now display returning user greeting.
        """
        reg_resp = self.client.post('/get-started', data={
            'full_name': 'Jordan Lee',
            'email': 'jordan@example.com',
            'password': 'SecurePass2026!',
            'target_role': 'Cloud Architect'
        }, follow_redirects=True)
        self.assertEqual(reg_resp.status_code, 200)
        first_html = reg_resp.get_data(as_text=True)
        self.assertIn("Welcome to CareerSkill AI,", first_html)

        # Second visit to dashboard
        second_resp = self.client.get('/dashboard')
        self.assertEqual(second_resp.status_code, 200)
        second_html = second_resp.get_data(as_text=True)

        self.assertIn("Welcome back,", second_html)
        self.assertIn("Jordan Lee", second_html)
        self.assertIn("Continue your journey toward", second_html)
        self.assertNotIn("Welcome to CareerSkill AI,", second_html)

    def test_existing_users_are_treated_as_returning_users(self):
        """
        Verify existing / pre-created users in DB are not treated as new users.
        """
        with self.app.app_context():
            u = User(full_name="Existing Veteran", email="veteran@example.com", first_login=False)
            u.set_password("OldPassword123!")
            db.session.add(u)
            db.session.commit()

            tc = TargetCareer(user_id=u.id, career_name="Full Stack Developer", normalized_career_name="Full Stack Developer")
            db.session.add(tc)
            up = UserProfile(user_id=u.id)
            db.session.add(up)
            db.session.commit()

        login_resp = self.client.post('/login', data={
            'email': 'veteran@example.com',
            'password': 'OldPassword123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        html = login_resp.get_data(as_text=True)

        self.assertIn("Welcome back,", html)
        self.assertIn("Existing Veteran", html)
        self.assertIn("Continue your journey toward", html)
        self.assertIn("Full Stack Developer", html)
        self.assertNotIn("Welcome to CareerSkill AI,", html)


if __name__ == '__main__':
    unittest.main()
