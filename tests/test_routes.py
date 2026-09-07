import unittest
import json
from app import create_app
from models import db, User, CareerProfile

class RoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_get_started_page_elements(self):
        """Test that get_started.html contains custom input and suggestion chips."""
        response = self.client.get('/get-started')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Verify field label
        self.assertIn("What career or job role do you want?", html)
        # Verify placeholder
        self.assertIn("e.g., Data Analyst, AI Engineer, Business Analyst...", html)
        # Verify popular roles suggestion chips
        self.assertIn("Popular roles:", html)
        self.assertIn("Data Analyst", html)
        self.assertIn("Data Scientist", html)
        self.assertIn("Business Analyst", html)
        self.assertIn("AI Engineer", html)
        self.assertIn("ML Engineer", html)
        self.assertIn("Product Analyst", html)
        self.assertIn("Financial Analyst", html)
        self.assertIn("Cybersecurity Analyst", html)
        self.assertIn("Cloud Engineer", html)
        self.assertIn("Software Developer", html)
        # Verify Register & Begin Assessment button
        self.assertIn("Register & Begin Assessment", html)

    def test_api_exact_role_analysis(self):
        """Test API endpoint with exact role (Data Analyst)."""
        response = self.client.post(
            '/api/analyze-career',
            data=json.dumps({'career_role': 'Data Analyst'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['target_role'], 'Data Analyst')
        self.assertEqual(data['confidence_score'], 100)
        self.assertEqual(data['market_status'], 'Verified Industry Benchmark')
        self.assertIn('SQL', data['matched_skills'])

    def test_api_custom_role_healthcare_data_analyst(self):
        """Test API endpoint with custom role (Healthcare Data Analyst)."""
        response = self.client.post(
            '/api/analyze-career',
            data=json.dumps({'career_role': 'Healthcare Data Analyst'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['target_role'], 'Healthcare Data Analyst')
        self.assertTrue(data['is_custom_role'])
        self.assertEqual(data['market_status'], 'Estimated Market Requirements')
        self.assertGreaterEqual(data['confidence_score'], 80)
        self.assertIn("We couldn't find enough exact market data for 'Healthcare Data Analyst'", data['explanation'])
        self.assertTrue(any('Data Analyst' in r for r in data['related_roles']))

    def test_api_empty_role_rejection(self):
        """Test API endpoint with empty input."""
        response = self.client.post(
            '/api/analyze-career',
            data=json.dumps({'career_role': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Please enter the career or job role you want to pursue.")

    def test_register_and_create_career_profile(self):
        """Test registration flow saving user and career profile in SQLite."""
        post_data = {
            'full_name': 'Alex Smith',
            'email': 'alex@example.com',
            'password': 'secretpassword',
            'target_role': 'Healthcare Data Analyst'
        }
        response = self.client.post('/get-started', data=post_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn("Healthcare Data Analyst", html)
        self.assertIn("Dashboard", html)

        # Check DB directly
        with self.app.app_context():
            user = User.query.filter_by(email='alex@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, 'Alex Smith')

            profile = CareerProfile.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(profile)
            self.assertEqual(profile.target_role, 'Healthcare Data Analyst')
            self.assertTrue(profile.is_custom_role)
            self.assertGreaterEqual(profile.confidence_score, 80)
            self.assertEqual(profile.market_status, 'Estimated Market Requirements')

if __name__ == '__main__':
    unittest.main()
