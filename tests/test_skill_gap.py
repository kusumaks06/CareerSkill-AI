import json
import unittest
from datetime import datetime, timezone
from app import create_app
from models import db, User, UserProfile, UserSkill, TargetCareer, SkillGapAnalysis, SkillGapItem
from services.skill_normalizer import normalize_skill, skills_match, find_matching_skill
from services.skill_gap_service import skill_gap_service


class TestSkillGapAnalysis(unittest.TestCase):
    """Test suite for the data-driven Skill Gap Analysis Engine."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_skill_normalization(self):
        """Test canonical mapping for synonyms and variations."""
        self.assertEqual(normalize_skill('powerbi')[0], 'Power BI')
        self.assertEqual(normalize_skill('Microsoft Power BI')[0], 'Power BI')
        self.assertEqual(normalize_skill('MS Power BI')[0], 'Power BI')
        self.assertEqual(normalize_skill('postgresql')[0], 'SQL')
        self.assertEqual(normalize_skill('Postgres')[0], 'SQL')
        self.assertEqual(normalize_skill('ML')[0], 'Machine Learning')
        self.assertEqual(normalize_skill('sklearn')[0], 'Scikit-learn')
        self.assertEqual(normalize_skill('NLP')[0], 'Natural Language Processing (NLP)')
        self.assertEqual(normalize_skill('LLM')[0], 'Large Language Models (LLMs)')

    def test_skills_match(self):
        """Test matching logic between user input and target canonical skills."""
        self.assertTrue(skills_match('powerbi', 'Power BI'))
        self.assertTrue(skills_match('PostgreSQL', 'SQL'))
        self.assertTrue(skills_match('Machine Learning', 'ml'))
        self.assertFalse(skills_match('Python', 'SQL'))

    def test_market_requirements_exact_match(self):
        """Test exact benchmark retrieval for Data Analyst."""
        market_data = skill_gap_service.get_market_requirements_for_role('Data Analyst')
        self.assertFalse(market_data['is_custom_role'])
        self.assertEqual(market_data['market_status'], 'Verified Industry Benchmark')
        skill_names = [s['skill'] for s in market_data['skills']]
        self.assertIn('SQL', skill_names)
        self.assertIn('Python', skill_names)
        self.assertIn('Excel', skill_names)
        self.assertIn('Power BI', skill_names)

    def test_market_requirements_custom_role_synthesis(self):
        """Test NLP TF-IDF cosine similarity & domain synthesis for custom roles."""
        custom_data = skill_gap_service.get_market_requirements_for_role('Healthcare Data Analyst')
        self.assertTrue(custom_data['is_custom_role'])
        self.assertEqual(custom_data['market_status'], 'Estimated Market Requirements')
        skill_names = [s['skill'] for s in custom_data['skills']]
        self.assertIn('SQL', skill_names)
        # Verify healthcare domain enrichment
        self.assertTrue(any('Healthcare' in s or 'Clinical' in s or 'Biostatistics' in s for s in skill_names))

    def test_skill_gap_analysis_calculation(self):
        """
        Verify the exact user scenario requested:
        Target: Data Analyst
        User skills:
          - Python: Intermediate (50)
          - SQL: Beginner (25)
          - Excel: Intermediate (50)
          - Power BI: Beginner (25)
        """
        # Create User
        user = User(full_name='Test Analyst', email='analyst@example.com')
        user.set_password('SecurePass123')
        db.session.add(user)
        db.session.commit()

        # Add Profile
        profile = UserProfile(
            user_id=user.id,
            education='BE',
            degree='BE',
            branch='AI & Data Science',
            learning_hours_per_day='2 hours/day',
            learning_days_per_week=5,
            learning_hours_per_week=10.0
        )
        db.session.add(profile)

        # Add Target Career
        tc = TargetCareer(user_id=user.id, career_name='Data Analyst', normalized_career_name='data analyst')
        db.session.add(tc)

        # Add Skills
        skills = [
            ('Python', 'Intermediate', 50),
            ('SQL', 'Beginner', 25),
            ('Excel', 'Intermediate', 50),
            ('Power BI', 'Beginner', 25)
        ]
        for name, level, score in skills:
            us = UserSkill(user_id=user.id, skill_name=name, confidence_level=3)
            us.set_proficiency(level)
            db.session.add(us)
        db.session.commit()

        # Run Analysis
        analysis = skill_gap_service.analyze_skill_gap(user=user, target_role='Data Analyst')

        # Assertions
        self.assertEqual(analysis['target_role'], 'Data Analyst')
        self.assertFalse(analysis['is_custom_role'])
        self.assertGreater(analysis['readiness_score'], 0)
        self.assertLessEqual(analysis['readiness_score'], 100)
        self.assertGreater(analysis['total_learning_hours'], 0)
        self.assertGreater(analysis['estimated_weeks'], 0)
        self.assertIsNotNone(analysis['completion_date'])

        # Check item statuses
        items_by_name = {i['normalized_skill_name']: i for i in analysis['gap_items']}

        # Python: Required Intermediate (50) vs User Intermediate (50) -> Strong
        self.assertEqual(items_by_name['Python']['status'], 'STRONG')
        self.assertEqual(items_by_name['Python']['gap_score'], 0)

        # SQL: Required Advanced (75) vs User Beginner (25) -> Partial Gap (50)
        self.assertEqual(items_by_name['SQL']['status'], 'PARTIAL')
        self.assertEqual(items_by_name['SQL']['gap_score'], 50)
        self.assertIn(items_by_name['SQL']['priority'], ('Critical', 'High'))

        # Excel: Required Advanced (75) vs User Intermediate (50) -> Partial Gap (25)
        self.assertEqual(items_by_name['Excel']['status'], 'PARTIAL')
        self.assertEqual(items_by_name['Excel']['gap_score'], 25)

        # Power BI: Required Intermediate (50) vs User Beginner (25) -> Partial Gap (25)
        self.assertEqual(items_by_name['Power BI']['status'], 'PARTIAL')
        self.assertEqual(items_by_name['Power BI']['gap_score'], 25)

        # Missing skill (e.g. Data Cleaning or Statistics)
        self.assertEqual(items_by_name['Data Cleaning']['status'], 'MISSING')
        self.assertEqual(items_by_name['Data Cleaning']['user_score'], 0)

        # Recommendations should be populated
        self.assertGreaterEqual(len(analysis['recommendations']), 1)

        # Save to DB & verify persistence
        saved = skill_gap_service.save_analysis_to_db(user.id, analysis)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.user_id, user.id)
        self.assertEqual(len(saved.items), len(analysis['gap_items']))

    def test_interactive_topic_assessment_ajax(self):
        """Test the AJAX endpoint for refining known topics interactively."""
        user = User(full_name='Topic Tester', email='topic@example.com')
        user.set_password('Pass1234')
        db.session.add(user)
        db.session.commit()

        tc = TargetCareer(user_id=user.id, career_name='Data Analyst', normalized_career_name='data analyst')
        db.session.add(tc)
        db.session.commit()

        # Login session
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        # Send AJAX topic evaluation for SQL
        response = self.client.post('/api/assess-topics', json={
            'user_id': user.id,
            'target_role': 'Data Analyst',
            'skill_name': 'SQL',
            'checked_topics': [
                'SELECT & WHERE Filtering',
                'Aggregations & GROUP BY / HAVING',
                'INNER, LEFT & RIGHT JOINs'
            ]
        })

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('analysis', data)
        self.assertIn('gauge_json', data)

        # Check updated SQL remaining topics
        gap_items = data['analysis']['gap_items']
        sql_item = next(i for i in gap_items if i['normalized_skill_name'] == 'SQL')
        known_names = [t['name'] if isinstance(t, dict) else t for t in sql_item['known_topics']]
        self.assertIn('SELECT & WHERE Filtering', known_names)
        self.assertIn('INNER, LEFT & RIGHT JOINs', known_names)

    def test_career_analysis_view_route(self):
        """Test GET /career-analysis route returns HTTP 200 with complete dashboard."""
        user = User(full_name='Route Candidate', email='route@example.com')
        user.set_password('Pass1234')
        db.session.add(user)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/career-analysis')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Career Gap Analysis', html)
        self.assertIn('Career Readiness', html)
        self.assertIn('chart-gauge', html)
        self.assertIn('Detailed Skill & Topic Gap Matrix', html)
        self.assertIn('Learning Roadmap Preview', html)


if __name__ == '__main__':
    unittest.main()
