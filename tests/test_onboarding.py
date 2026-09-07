import unittest
import json
from app import create_app
from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    PROFICIENCY_SCORE_MAP
)

class OnboardingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_proficiency_score_mapping(self):
        """Verify numerical scoring for all skill proficiency tiers."""
        self.assertEqual(PROFICIENCY_SCORE_MAP['Beginner'], 25)
        self.assertEqual(PROFICIENCY_SCORE_MAP['Intermediate'], 50)
        self.assertEqual(PROFICIENCY_SCORE_MAP['Advanced'], 75)
        self.assertEqual(PROFICIENCY_SCORE_MAP['Expert'], 100)
        self.assertEqual(PROFICIENCY_SCORE_MAP["I don't know this skill"], 0)
        self.assertEqual(PROFICIENCY_SCORE_MAP['No Knowledge'], 0)

    def test_onboarding_page_render(self):
        """Verify onboarding template renders all 7 steps and elements."""
        response = self.client.get('/onboarding?role=Healthcare+Data+Analyst')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Check Steps & Titles
        self.assertIn("Tell us about your background", html)
        self.assertIn("BE / BTech", html)
        self.assertIn("Artificial Intelligence & Data Science", html)
        self.assertIn("What skills do you already have?", html)
        self.assertIn("How much time can you realistically spend learning?", html)
        self.assertIn("How do you prefer to learn?", html)
        self.assertIn("What is your main career goal?", html)
        self.assertIn("YOUR CAREER PROFILE", html)
        self.assertIn("Analyze My Career Gap", html)

    def test_complete_onboarding_submission_and_persistence(self):
        """Test submitting complete onboarding data and verify SQLite persistence."""
        skills_payload = [
            {'name': 'Python', 'proficiency': 'Intermediate', 'confidence': 4},
            {'name': 'SQL', 'proficiency': 'Beginner', 'confidence': 3},
            {'name': 'Healthcare Analytics', 'proficiency': 'Advanced', 'confidence': 5},
            {'name': 'HL7 Data Standards', 'proficiency': "I don't know this skill", 'confidence': 1}
        ]
        prefs_payload = ['Video Courses', 'Hands-on Practice', 'Projects']
        goals_payload = ['Get my first job', 'Build a portfolio']

        post_data = {
            'target_role': 'Healthcare Data Analyst',
            'full_name': 'Kusuma K S',
            'email': 'kusuma@example.com',
            'highest_education': "Undergraduate / Bachelor's",
            'degree': 'BE / BTech',
            'branch': 'Artificial Intelligence & Data Science',
            'graduation_year': '2026',
            'current_status': 'Student',
            'experience_level': 'No experience',
            'has_projects_radio': 'yes',
            'project_experience': 'Heart Disease Prediction using Machine Learning',
            'learning_hours_per_day': '2 hours/day',
            'learning_days_per_week': '5',
            'learning_hours_per_week': '10.0',
            'preferred_difficulty': 'Balanced',
            'learning_prefs_json': json.dumps(prefs_payload),
            'career_goals_json': json.dumps(goals_payload),
            'skills_data_json': json.dumps(skills_payload)
        }

        response = self.client.post('/onboarding', data=post_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Verify redirection to career-analysis
        self.assertIn("Career Gap Analysis", html)
        self.assertIn("Healthcare Data Analyst", html)
        self.assertIn("Python", html)
        self.assertIn("Healthcare Analytics", html)

        # Direct DB Assertions
        with self.app.app_context():
            user = User.query.filter_by(email='kusuma@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, 'Kusuma K S')

            # Verify TargetCareer
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(tc)
            self.assertEqual(tc.career_name, 'Healthcare Data Analyst')

            # Verify UserProfile
            profile = UserProfile.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(profile)
            self.assertEqual(profile.degree, 'BE / BTech')
            self.assertEqual(profile.branch, 'Artificial Intelligence & Data Science')
            self.assertEqual(profile.graduation_year, '2026')
            self.assertEqual(profile.current_status, 'Student')
            self.assertEqual(profile.learning_hours_per_week, 10.0)
            self.assertTrue(profile.has_project_experience)
            self.assertIn('Video Courses', profile.get_learning_preferences())
            self.assertIn('Get my first job', profile.get_career_goals())

            # Verify UserSkills & Score Conversion
            skills = UserSkill.query.filter_by(user_id=user.id).all()
            self.assertEqual(len(skills), 4)
            
            skill_dict = {s.skill_name: (s.proficiency_level, s.proficiency_score, s.confidence_level) for s in skills}
            self.assertEqual(skill_dict['Python'], ('Intermediate', 50, 4))
            self.assertEqual(skill_dict['SQL'], ('Beginner', 25, 3))
            self.assertEqual(skill_dict['Healthcare Analytics'], ('Advanced', 75, 5))
            self.assertEqual(skill_dict['HL7 Data Standards'], ("I don't know this skill", 0, 1))

    def test_onboarding_validation_missing_skills(self):
        """Test rejection when skills list is empty."""
        post_data = {
            'target_role': 'Data Analyst',
            'full_name': 'Test User',
            'email': 'test@example.com',
            'highest_education': "Undergraduate / Bachelor's",
            'degree': 'BE / BTech',
            'branch': 'Computer Science',
            'skills_data_json': '[]'  # Empty skills
        }
        response = self.client.post('/onboarding', data=post_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Please add at least one current skill before proceeding.", html)

if __name__ == '__main__':
    unittest.main()
