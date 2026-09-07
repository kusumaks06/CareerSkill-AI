import unittest
import json
from datetime import datetime, timezone
from app import create_app
from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    CareerProfile, 
    SkillGapAnalysis,
    Course,
    CourseProgress,
    CourseFeedback,
    Suggestion,
    AssessmentQuestion,
    AssessmentAttempt,
    UserRoadmap,
    RoadmapMilestone,
    LearningActivity
)

class FinalIntegrationTestCase(unittest.TestCase):
    """
    FINAL MODULE INTEGRATION TEST SUITE
    Verifies all 25 checkpoints from end-to-end:
    Welcome -> Register -> Login -> Career Analysis -> Free text job role ->
    Market Requirements -> Current Skills -> Skill Gap -> Recommendations ->
    Roadmap -> Trends & Salary -> Skill Assessment -> Learning Progress ->
    Course Completion -> Feedback -> Suggestions -> Admin Management -> Security.
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

    def test_complete_25_checkpoint_integration(self):
        # ----------------------------------------------------
        # 1. Unauthenticated Security: No market data on Get Started / Register
        # ----------------------------------------------------
        get_started_resp = self.client.get('/get-started')
        self.assertEqual(get_started_resp.status_code, 200)
        gs_html = get_started_resp.get_data(as_text=True)
        self.assertIn("Create Your Account", gs_html)
        self.assertNotIn("marketAnalysisCard", gs_html)
        self.assertNotIn("Career Readiness Gauge", gs_html)

        # ----------------------------------------------------
        # 2. Registration works (Checkpoints 1 & 21)
        # ----------------------------------------------------
        reg_resp = self.client.post('/register', data={
            'full_name': 'Taylor Analyst',
            'email': 'taylor@example.com',
            'password': 'SecurePassword2026!',
            'target_role': 'Healthcare Data Analyst'
        }, follow_redirects=True)
        self.assertEqual(reg_resp.status_code, 200)
        self.assertIn("Dashboard", reg_resp.get_data(as_text=True))

        with self.app.app_context():
            user = User.query.filter_by(email='taylor@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.full_name, 'Taylor Analyst')
            self.assertTrue(user.check_password('SecurePassword2026!'))
            user_id = user.id

        # ----------------------------------------------------
        # 3. Logout works (Checkpoint 3)
        # ----------------------------------------------------
        logout_resp = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)
        self.assertIn("Login", logout_resp.get_data(as_text=True))

        # ----------------------------------------------------
        # 4. Forgot Password & OTP Reset works (Checkpoints 4 & 5)
        # ----------------------------------------------------
        fp_resp = self.client.post('/forgot-password', data={'email': 'taylor@example.com'}, follow_redirects=True)
        self.assertEqual(fp_resp.status_code, 200)
        self.assertIn("Verify your email", fp_resp.get_data(as_text=True))

        with self.app.app_context():
            from models import PasswordResetOTP
            otp_record = PasswordResetOTP.query.filter_by(user_id=user_id).order_by(PasswordResetOTP.id.desc()).first()
            self.assertIsNotNone(otp_record)
            otp_record.set_otp('654321')
            db.session.commit()

        # Verify OTP
        v_resp = self.client.post('/verify-otp', data={'otp': '654321'}, follow_redirects=True)
        self.assertEqual(v_resp.status_code, 200)
        self.assertIn("Create a new password", v_resp.get_data(as_text=True))

        # Reset Password
        rp_resp = self.client.post('/reset-password', data={
            'new_password': 'NewStrongPassword2026!',
            'confirm_password': 'NewStrongPassword2026!'
        }, follow_redirects=True)
        self.assertEqual(rp_resp.status_code, 200)
        self.assertIn("Your password has been reset successfully", rp_resp.get_data(as_text=True))

        # ----------------------------------------------------
        # 5. Login works with new password (Checkpoint 2)
        # ----------------------------------------------------
        login_resp = self.client.post('/login', data={
            'email': 'taylor@example.com',
            'password': 'NewStrongPassword2026!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        l_html = login_resp.get_data(as_text=True)
        self.assertIn("Welcome back,", l_html)
        self.assertIn("Taylor Analyst", l_html)

        # ----------------------------------------------------
        # 6. Career Analysis & Custom Roles (Checkpoints 6, 7, 8)
        # ----------------------------------------------------
        # Test Data Analyst
        da_resp = self.client.get('/career-analysis?role=Data+Analyst')
        self.assertEqual(da_resp.status_code, 200)
        da_html = da_resp.get_data(as_text=True)
        self.assertIn("Career Gap Analysis:", da_html)
        self.assertIn("Data Analyst", da_html)
        self.assertIn("Verified Industry Benchmark", da_html)

        # Test Custom Role: Healthcare Data Analyst (no crash)
        hda_resp = self.client.get('/career-analysis?role=Healthcare+Data+Analyst')
        self.assertEqual(hda_resp.status_code, 200)
        hda_html = hda_resp.get_data(as_text=True)
        self.assertIn("Healthcare Data Analyst", hda_html)
        self.assertIn("Estimated Market Requirements", hda_html)

        # Test AI Engineer (no crash)
        ai_resp = self.client.get('/career-analysis?role=AI+Engineer')
        self.assertEqual(ai_resp.status_code, 200)
        ai_html = ai_resp.get_data(as_text=True)
        self.assertIn("AI Engineer", ai_html)

        # Test Financial Analyst (no crash)
        fin_resp = self.client.get('/career-analysis?role=Financial+Analyst')
        self.assertEqual(fin_resp.status_code, 200)
        fin_html = fin_resp.get_data(as_text=True)
        self.assertIn("Financial Analyst", fin_html)

        # ----------------------------------------------------
        # 7. Update User Skills & Recalculate Gap (Checkpoints 7 & 8)
        # ----------------------------------------------------
        skill_update_resp = self.client.post('/career-analysis/update-skills', data={
            'target_role': 'Data Analyst',
            'total_skills_count': '3',
            'skill_name_0': 'SQL',
            'skill_level_0': 'Intermediate',
            'skill_name_1': 'Python',
            'skill_level_1': 'Beginner',
            'skill_name_2': 'Tableau',
            'skill_level_2': 'Beginner'
        }, follow_redirects=True)
        self.assertEqual(skill_update_resp.status_code, 200)
        su_html = skill_update_resp.get_data(as_text=True)
        self.assertIn("SQL", su_html)
        self.assertIn("Intermediate", su_html)

        # ----------------------------------------------------
        # 8. Course Recommendations using Skill Gaps (Checkpoint 9)
        # ----------------------------------------------------
        courses_resp = self.client.get('/course-recommendations?role=Data+Analyst')
        self.assertEqual(courses_resp.status_code, 200)
        courses_html = courses_resp.get_data(as_text=True)
        self.assertIn("Personalized Learning Recommendations", courses_html)
        self.assertIn("SQL", courses_html)

        # ----------------------------------------------------
        # 9. Career Roadmap using Gaps & Weekly Hours (Checkpoint 10)
        # ----------------------------------------------------
        roadmap_resp = self.client.get('/roadmap?role=Data+Analyst')
        self.assertEqual(roadmap_resp.status_code, 200)
        roadmap_html = roadmap_resp.get_data(as_text=True)
        self.assertIn("AI Career Learning Roadmap", roadmap_html)
        self.assertIn("Data Analyst", roadmap_html)

        # ----------------------------------------------------
        # 10. Market Trends & Salary (Checkpoint 11)
        # ----------------------------------------------------
        trends_resp = self.client.get('/market-trends?role=all&currency=usd')
        self.assertEqual(trends_resp.status_code, 200)
        trends_html = trends_resp.get_data(as_text=True)
        self.assertIn("Market Trend Analytics", trends_html)
        self.assertIn("Salary Benchmark", trends_html)

        # Test INR Currency
        trends_inr_resp = self.client.get('/market-trends?currency=inr')
        self.assertEqual(trends_inr_resp.status_code, 200)

        # ----------------------------------------------------
        # 11. Skill Assessment (Checkpoint 12)
        # ----------------------------------------------------
        assess_hub_resp = self.client.get('/assessment-hub')
        self.assertEqual(assess_hub_resp.status_code, 200)
        self.assertIn("AI Skill Assessment", assess_hub_resp.get_data(as_text=True))

        # Start Assessment
        start_assess = self.client.get('/assessment/start/SQL')
        self.assertEqual(start_assess.status_code, 200)

        # Submit Assessment
        submit_assess = self.client.post('/assessment/submit', data={
            'skill_name': 'SQL',
            'target_role': 'Data Analyst',
            'q_1': 'B',
            'q_2': 'A'
        }, follow_redirects=True)
        self.assertEqual(submit_assess.status_code, 200)
        self.assertIn("Assessment Report", submit_assess.get_data(as_text=True))

        # ----------------------------------------------------
        # 12. Learning Progress Tracking (Checkpoint 13)
        # ----------------------------------------------------
        progress_resp = self.client.get('/progress')
        self.assertEqual(progress_resp.status_code, 200)
        self.assertIn("Learning Progress", progress_resp.get_data(as_text=True))

        # Log study session
        log_sess_resp = self.client.post('/api/progress/log-session', data={
            'hours_spent': '2.5',
            'skill_practiced': 'SQL',
            'notes': 'Completed window functions exercises'
        }, follow_redirects=True)
        self.assertEqual(log_sess_resp.status_code, 200)

        # ----------------------------------------------------
        # 13. Course Completion & Feedback (Checkpoints 14 & 15)
        # ----------------------------------------------------
        complete_course_resp = self.client.get('/course/1/complete', follow_redirects=True)
        self.assertEqual(complete_course_resp.status_code, 200)
        self.assertIn("Course Feedback", complete_course_resp.get_data(as_text=True))

        # Submit Feedback
        feedback_resp = self.client.post('/course/1/feedback', data={
            'rating': '5',
            'usefulness': 'Very Useful',
            'improved_skill': 'Yes',
            'liked_aspects': 'Great hands-on SQL queries and explanation',
            'improvement_suggestions': 'Add more optimization tips',
            'would_recommend': 'Yes'
        }, follow_redirects=True)
        self.assertEqual(feedback_resp.status_code, 200)
        self.assertIn("Thank you! Your course feedback has been submitted successfully.", feedback_resp.get_data(as_text=True))

        # ----------------------------------------------------
        # 14. Suggestions & Feedback System (Checkpoint 16)
        # ----------------------------------------------------
        sug_view_resp = self.client.get('/suggestions')
        self.assertEqual(sug_view_resp.status_code, 200)
        self.assertIn("Suggestions & Feedback", sug_view_resp.get_data(as_text=True))

        # Submit Suggestion
        submit_sug_resp = self.client.post('/suggestions', data={
            'category': 'Missing Course',
            'title': 'Add Advanced PySpark Course',
            'description': 'PySpark is in high demand for Big Data engineering roles.',
            'career': 'Data Engineer',
            'skill': 'PySpark'
        }, follow_redirects=True)
        self.assertEqual(submit_sug_resp.status_code, 200)
        self.assertIn("Thank you! Your suggestion has been submitted successfully for review.", submit_sug_resp.get_data(as_text=True))

        # ----------------------------------------------------
        # 15. Admin Access Control & Dashboard (Checkpoints 17, 18, 19, 20)
        # ----------------------------------------------------
        # Regular user accessing admin dashboard -> 403 Forbidden
        admin_blocked_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_blocked_resp.status_code, 403)

        # Create and login as Admin
        with self.app.app_context():
            admin_user = User(
                full_name='Platform Admin',
                email='admin@careerskill.ai',
                is_admin=True,
                role='admin'
            )
            admin_user.set_password('AdminMaster2026!')
            db.session.add(admin_user)
            db.session.commit()

        admin_login_resp = self.client.post('/login', data={
            'email': 'admin@careerskill.ai',
            'password': 'AdminMaster2026!'
        }, follow_redirects=True)
        self.assertEqual(admin_login_resp.status_code, 200)

        # Admin Dashboard Works
        admin_dash_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_dash_resp.status_code, 200)
        ad_html = admin_dash_resp.get_data(as_text=True)
        self.assertIn("Admin Dashboard", ad_html)
        self.assertIn("Total Users", ad_html)
        self.assertIn("Feedback Received", ad_html)
        self.assertIn("Suggestions Received", ad_html)

        # Admin Analytics Works
        admin_analytics_resp = self.client.get('/admin/analytics')
        self.assertEqual(admin_analytics_resp.status_code, 200)
        self.assertIn("Enterprise Analytics", admin_analytics_resp.get_data(as_text=True))

        # Admin Users View Works
        admin_users_resp = self.client.get('/admin/users')
        self.assertEqual(admin_users_resp.status_code, 200)
        self.assertIn("User Management", admin_users_resp.get_data(as_text=True))

        # Admin Feedback View Works
        admin_fb_resp = self.client.get('/admin/feedback')
        self.assertEqual(admin_fb_resp.status_code, 200)
        self.assertIn("Course Feedback", admin_fb_resp.get_data(as_text=True))

        # Admin Suggestions View Works
        admin_sug_resp = self.client.get('/admin/suggestions')
        self.assertEqual(admin_sug_resp.status_code, 200)
        self.assertIn("User Suggestions", admin_sug_resp.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
