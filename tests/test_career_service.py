import unittest
from services.career_service import career_service

class CareerServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.service = career_service

    def test_exact_role_match(self):
        """Test exact benchmark role matching (e.g., Data Analyst)."""
        result = self.service.analyze_career_role("Data Analyst")
        self.assertTrue(result['success'])
        self.assertFalse(result['is_custom_role'])
        self.assertEqual(result['confidence_score'], 100)
        self.assertEqual(result['market_status'], 'Verified Industry Benchmark')
        self.assertIn('SQL', result['matched_skills'])
        self.assertIn('Python', result['matched_skills'])

    def test_custom_role_nlp_estimation(self):
        """Test custom role (Healthcare Data Analyst) similarity and skill synthesis."""
        result = self.service.analyze_career_role("Healthcare Data Analyst")
        self.assertTrue(result['success'])
        self.assertTrue(result['is_custom_role'])
        self.assertEqual(result['target_role'], 'Healthcare Data Analyst')
        self.assertEqual(result['market_status'], 'Estimated Market Requirements')
        # Check confidence is in high realistic estimated range (82%)
        self.assertGreaterEqual(result['confidence_score'], 80)
        self.assertIn("We couldn't find enough exact market data for 'Healthcare Data Analyst'", result['explanation'])
        self.assertTrue(any('Data Analyst' in r for r in result['related_roles']))
        # Verify both core analytics and healthcare domain skills are synthesized
        self.assertTrue(any(s in result['matched_skills'] for s in ['SQL', 'Python', 'Excel', 'Power BI']))
        self.assertTrue(any('Healthcare' in s or 'Clinical' in s for s in result['matched_skills']))

    def test_empty_role_validation(self):
        """Test empty or whitespace-only role rejection."""
        result = self.service.analyze_career_role("")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Please enter the career or job role you want to pursue.")

        result_spaces = self.service.analyze_career_role("   ")
        self.assertFalse(result_spaces['success'])
        self.assertEqual(result_spaces['error'], "Please enter the career or job role you want to pursue.")

    def test_custom_sports_data_scientist(self):
        """Test another custom role: Sports Data Scientist."""
        result = self.service.analyze_career_role("Sports Data Scientist")
        self.assertTrue(result['success'])
        self.assertTrue(result['is_custom_role'])
        self.assertEqual(result['market_status'], 'Estimated Market Requirements')
        self.assertTrue(any('Data Scientist' in r for r in result['related_roles']))
        self.assertTrue(any('Sports' in s or 'Python' in s for s in result['matched_skills']))

if __name__ == '__main__':
    unittest.main()
