import unittest
from app import create_app

class BasicTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('development')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_welcome_page(self):
        """Test that the index/welcome page loads with required content."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        
        self.assertIn("CareerSkill AI", html)
        self.assertIn("Learn what matters. Build the skills that matter. Reach the career you want.", html)
        self.assertIn("Get Started", html)
        self.assertIn("Login", html)

    def test_auth_routes_load(self):
        """Test login and get-started routes return 200."""
        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 200)
        
        res_get_started = self.client.get('/get-started')
        self.assertEqual(res_get_started.status_code, 200)

if __name__ == '__main__':
    unittest.main()

