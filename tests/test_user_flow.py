import unittest
import json
from app import create_app
from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    CareerProfile, 
    SkillGapAnalysis
)

class UserFlowTestCase(unittest.TestCase):
    """
    Test suite verifying the complete CareerSkill AI User Flow:
    WELCOME -> REGISTER / LOGIN -> USER DASHBOARD -> ENTER TARGET CAREER -> 
    MARKET ANALYSIS -> REQUIRED SKILLS -> CURRENT SKILLS -> SKILL GAP ANALYSIS -> 
    COURSE RECOMMENDATIONS -> ROADMAP.
    """
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_step1_get_started_logged_out_has_no_market_data(self):
        """
        Test 1 & 2:
        Open Get Started while logged out.
        Verify:
        - Welcome message, Name, Email, Password, Target Career input, Register button, Login link are present.
        - NO market analysis, NO market confidence, NO core skills list, NO salary info, NO recommendations are displayed.
        """
        response = self.client.get('/get-started')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Verified required elements present
        self.assertIn("Create Your Account", html)
        self.assertIn("full_name", html)
        self.assertIn("email", html)
        self.assertIn("password", html)
        self.assertIn("target_role", html)
        self.assertIn("Register", html)
        self.assertIn("Login here", html)

        # Verified NO market analysis/skills/salary/gap data rendered before authentication
        self.assertNotIn("Identified Core Skills to Assess", html)
        self.assertNotIn("marketAnalysisCard", html)
        self.assertNotIn("confidence-badge", html)
        self.assertNotIn("Salary Benchmark", html)
        self.assertNotIn("Career Readiness Gauge", html)

    def test_step2_unauthenticated_career_analysis_redirects_to_login(self):
        """Verify unauthenticated access to /career-analysis is strictly blocked and redirects to /login."""
        # Unauthenticated request (no session)
        self.app.config['TESTING'] = False
        try:
            response = self.client.get('/career-analysis')
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login', response.location)
        finally:
            self.app.config['TESTING'] = True

    def test_step3_complete_user_flow_e2e(self):
        """
        Test complete end-to-end user flow:
        1. Register with Target Career 'Data Analyst'
        2. Lands on Dashboard
        3. Dashboard has target career & 'Analyze Career' launcher
        4. Navigate to Career Analysis for 'Data Analyst'
        5. Verify market requirements & required skills appear
        6. Update current skills via /career-analysis/update-skills
        7. Verify updated skill gap analysis (readiness score, known topics, remaining topics, hours)
        8. Navigate to Course Recommendations and Roadmap
        9. Switch target role to 'Healthcare Data Analyst' and verify analysis updates
        """
        # 1. Register
        reg_resp = self.client.post('/get-started', data={
            'full_name': 'Morgan Data',
            'email': 'morgan@example.com',
            'password': 'SecurePassword123!',
            'target_role': 'Data Analyst'
        }, follow_redirects=True)
        self.assertEqual(reg_resp.status_code, 200)
        reg_html = reg_resp.get_data(as_text=True)

        # 2. Lands on Dashboard
        self.assertIn("Welcome to CareerSkill AI,", reg_html)
        self.assertNotIn("Welcome back,", reg_html)
        self.assertIn("Morgan Data", reg_html)
        self.assertIn("User Dashboard", reg_html)
        self.assertIn("Data Analyst", reg_html)
        self.assertIn("Enter Target Career & Run Analysis", reg_html)

        with self.app.app_context():
            user = User.query.filter_by(email='morgan@example.com').first()
            self.assertIsNotNone(user)
            user_id = user.id

        # 3. Open Career Analysis as logged-in user
        analysis_resp = self.client.get('/career-analysis?role=Data+Analyst')
        self.assertEqual(analysis_resp.status_code, 200)
        analysis_html = analysis_resp.get_data(as_text=True)

        # 4. Verify Market Analysis & Required Skills appear only after login
        self.assertIn("Career Gap Analysis:", analysis_html)
        self.assertIn("Data Analyst", analysis_html)
        self.assertIn("Verified Industry Benchmark", analysis_html)
        self.assertIn("SQL", analysis_html)
        self.assertIn("Python", analysis_html)
        self.assertIn("Career Readiness", analysis_html)
        self.assertIn("What are your current skills and proficiency levels?", analysis_html)

        # 5. User updates their current skills and proficiency
        update_resp = self.client.post('/career-analysis/update-skills', data={
            'target_role': 'Data Analyst',
            'total_skills_count': '3',
            'skill_name_0': 'SQL',
            'skill_level_0': 'Intermediate',
            'skill_name_1': 'Python',
            'skill_level_1': 'Beginner',
            'skill_name_2': 'Tableau',
            'skill_level_2': 'Beginner'
        }, follow_redirects=True)
        self.assertEqual(update_resp.status_code, 200)
        updated_html = update_resp.get_data(as_text=True)

        # 6. Verify skill gap analysis recalculated
        self.assertIn("Career Gap Analysis:", updated_html)
        self.assertIn("SQL", updated_html)
        self.assertIn("Intermediate", updated_html)
        self.assertIn("Required Study Time", updated_html)
        self.assertIn("Recommended Courses", updated_html)

        # 7. Check Course Recommendations
        recs_resp = self.client.get('/course-recommendations?role=Data+Analyst')
        self.assertEqual(recs_resp.status_code, 200)
        recs_html = recs_resp.get_data(as_text=True)
        self.assertIn("Personalized Learning Recommendations", recs_html)

        # 8. Check Roadmap
        roadmap_resp = self.client.get('/roadmap?role=Data+Analyst')
        self.assertEqual(roadmap_resp.status_code, 200)
        roadmap_html = roadmap_resp.get_data(as_text=True)
        self.assertIn("Roadmap", roadmap_html)

        # 9. Test entering and analyzing a custom/new career: Healthcare Data Analyst
        custom_resp = self.client.get('/career-analysis?role=Healthcare+Data+Analyst')
        self.assertEqual(custom_resp.status_code, 200)
        custom_html = custom_resp.get_data(as_text=True)
        self.assertIn("Healthcare Data Analyst", custom_html)
        self.assertIn("Estimated Market Requirements", custom_html)

    def test_step4_login_and_analyze_ai_engineer(self):
        """Test logging in with existing credentials and analyzing AI Engineer role."""
        # Create user
        with self.app.app_context():
            u = User(full_name="Sam Tech", email="sam@example.com")
            u.set_password("SamPass123!")
            db.session.add(u)
            db.session.commit()

        # Login
        login_resp = self.client.post('/login', data={
            'email': 'sam@example.com',
            'password': 'SamPass123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("Welcome back,", login_resp.get_data(as_text=True))

        # Enter and analyze AI Engineer
        ai_resp = self.client.get('/career-analysis?role=AI+Engineer')
        self.assertEqual(ai_resp.status_code, 200)
        ai_html = ai_resp.get_data(as_text=True)
        self.assertIn("Career Gap Analysis:", ai_html)
        self.assertIn("AI Engineer", ai_html)
        self.assertIn("Python", ai_html)
        self.assertIn("Machine Learning", ai_html)

if __name__ == '__main__':
    unittest.main()
