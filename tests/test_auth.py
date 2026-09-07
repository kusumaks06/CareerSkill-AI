import unittest
from app import create_app
from models import db, User, TargetCareer

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_user_registration_and_password_hashing(self):
        """Test that registration creates a user with securely hashed password."""
        post_data = {
            'full_name': 'Kusuma',
            'email': 'kusumaks682@gmail.com',
            'password': 'mysecretpassword123',
            'target_role': 'Data Analyst'
        }
        response = self.client.post('/get-started', data=post_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            user = User.query.filter_by(email='kusumaks682@gmail.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, 'Kusuma')
            self.assertNotEqual(user.password_hash, 'mysecretpassword123')
            self.assertTrue(user.check_password('mysecretpassword123'))
            self.assertFalse(user.check_password('wrongpassword'))

    def test_duplicate_email_registration(self):
        """Test duplicate registration returns friendly error without crashing."""
        post_data = {
            'full_name': 'Kusuma',
            'email': 'kusumaks682@gmail.com',
            'password': 'password123',
            'target_role': 'Data Analyst'
        }
        # First registration
        res1 = self.client.post('/get-started', data=post_data, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        # Duplicate registration
        res2 = self.client.post('/get-started', data=post_data, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        html = res2.get_data(as_text=True)
        self.assertIn("An account with this email already exists.", html)

    def test_login_and_logout_flow(self):
        """Test login with valid/invalid credentials and dashboard access."""
        # 1. Create user
        with self.app.app_context():
            user = User(full_name='Test User', email='test@example.com')
            user.set_password('correctpass')
            db.session.add(user)
            db.session.commit()

        # 2. Test invalid password
        res_fail = self.client.post('/login', data={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertIn("Invalid email or password.", res_fail.get_data(as_text=True))

        # 3. Test valid login -> redirects to dashboard
        res_login = self.client.post('/login', data={
            'email': 'test@example.com',
            'password': 'correctpass'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        login_html = res_login.get_data(as_text=True)
        self.assertIn("Login successful.", login_html)
        self.assertIn("Welcome back,", login_html)
        self.assertIn("Test User", login_html)

        # 4. Test accessing dashboard
        res_dash = self.client.get('/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn("User Dashboard", res_dash.get_data(as_text=True))

        # 5. Test logout
        res_logout = self.client.get('/logout', follow_redirects=True)
        self.assertIn("You have been logged out.", res_logout.get_data(as_text=True))

        # 6. Test dashboard redirects to login when logged out
        res_dash_after = self.client.get('/dashboard', follow_redirects=True)
        self.assertIn("Please log in to access your dashboard.", res_dash_after.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
