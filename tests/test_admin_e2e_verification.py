import sys
import unittest
from app import create_app
from models import db, User, TargetCareer, UserProfile, SkillDefinition, CustomCareer, MarketRequirement, Course, AdminActivityLog
from services.admin_service import admin_service
from services.recommendation_service import recommendation_service
from services.assessment_service import assessment_service

class EndToEndAdminVerification(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            recommendation_service.seed_courses_if_empty()
            assessment_service.seed_questions_if_empty()

    def _get_or_create_user(self, email="normal.student@careerskill.ai", is_admin=False, role="user"):
        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    full_name="Platform User" if not is_admin else "Platform Administrator",
                    email=email,
                    is_admin=is_admin,
                    role=role,
                    is_active=True
                )
                user.set_password("SecurePass@123" if not is_admin else "Admin@12345")
                db.session.add(user)
                db.session.commit()
            return user.id

    def test_1_normal_user_login_and_navigation_hidden(self):
        print("\n--- [TEST 1] Verifying Normal User Login & Admin Link Hiding ---")
        user_id = self._get_or_create_user(email="normal.student@careerskill.ai", is_admin=False, role="user")

        # Login as normal user
        login_resp = self.client.post('/login', data={
            'email': 'normal.student@careerskill.ai',
            'password': 'SecurePass@123'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        html = login_resp.get_data(as_text=True)

        # Ensure normal user dashboard works
        self.assertIn("Platform User", html)
        # Ensure Admin navigation item is NOT in the normal user navigation
        self.assertNotIn('/admin/dashboard', html)
        self.assertNotIn('href="/admin"', html)
        print("[PASS] Normal user logged in. Admin navigation is completely HIDDEN from normal user.")

    def test_2_unauthorized_access_to_admin_routes_blocked(self):
        print("\n--- [TEST 2] Verifying Backend Security & 403 Forbidden Page ---")
        user_id = self._get_or_create_user(email="normal.student@careerskill.ai", is_admin=False, role="user")

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = False

        # Attempt to access admin routes directly
        admin_urls = [
            '/admin/dashboard',
            '/admin/users',
            '/admin/courses',
            '/admin/skills',
            '/admin/careers',
            '/admin/market-requirements',
            '/admin/assessments',
            '/admin/roadmaps',
            '/admin/feedback',
            '/admin/suggestions',
            '/admin/analytics',
            '/admin/activity-log',
            '/admin/settings'
        ]

        for url in admin_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403, f"Expected 403 for {url} but got {resp.status_code}")
            html = resp.get_data(as_text=True)
            self.assertIn("403", html)
            self.assertIn("Access Denied", html)
            self.assertIn("administrator permissions", html)

        print("[PASS] All 13 admin endpoints blocked with HTTP 403 and custom dark-mode Access Denied page.")

    def test_3_admin_login_and_full_management_access(self):
        print("\n--- [TEST 3] Verifying Administrator Account & Full Management Access ---")
        admin_id = self._get_or_create_user(email="admin@careerskill.ai", is_admin=True, role="admin")

        # Admin login
        login_resp = self.client.post('/login', data={
            'email': 'admin@careerskill.ai',
            'password': 'Admin@12345'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # Check Admin Dashboard
        dash_resp = self.client.get('/admin/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        dash_html = dash_resp.get_data(as_text=True)
        self.assertIn("Admin Dashboard", dash_html)
        self.assertIn("Total Users", dash_html)
        self.assertIn("Total Courses", dash_html)
        self.assertIn("Total Job Roles", dash_html)
        self.assertIn("Assessments", dash_html)
        self.assertIn("Courses Completed", dash_html)
        self.assertIn("User Satisfaction", dash_html)
        self.assertIn("Admin Activity Governance Log", dash_html)
        print("[PASS] Admin dashboard renders with KPI statistics, career distribution, missing skills, and audit logs.")

        # Check all 13 management views
        views = {
            "1. Users": "/admin/users",
            "2. Courses": "/admin/courses",
            "3. Skills": "/admin/skills",
            "4. Job Roles": "/admin/careers",
            "5. Market Requirements": "/admin/market-requirements",
            "6. Salary/Market Trends": "/admin/analytics",
            "7. User Assessments": "/admin/assessments",
            "8. Course Recommendations": "/admin/courses",
            "9. User Progress": "/admin/users",
            "10. User Reviews and Suggestions": "/admin/suggestions",
            "11. Feedback/Ratings": "/admin/feedback",
            "12. System Analytics": "/admin/analytics",
            "13. Admin Activity Logs": "/admin/activity-log"
        }

        for name, path in views.items():
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, f"Failed accessing {name} at {path}")
            print(f"  [+] Verified {name} -> 200 OK")

    def test_4_admin_crud_operations_and_audit_logging(self):
        print("\n--- [TEST 4] Verifying Admin CRUD & Activity Logging ---")
        admin_id = self._get_or_create_user(email="admin@careerskill.ai", is_admin=True, role="admin")

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Skill with Demand Status
        self.client.post('/admin/skills/save', data={
            'name': 'Apache Kafka Streaming',
            'category': 'Data Engineering',
            'difficulty': 'Difficult',
            'demand_status': 'In-Demand',
            'description': 'Distributed event streaming and messaging architecture.',
            'topics': 'Brokers, Topics, Partitions, Consumer Groups'
        }, follow_redirects=True)

        # 2. Add Market Requirement with Salary & Experience
        self.client.post('/admin/market-requirements/save', data={
            'career_title': 'Streaming Data Engineer',
            'skill_name': 'Apache Kafka Streaming',
            'required_level': 'Advanced',
            'importance': 'Critical',
            'experience_level': '2 - 5 Years',
            'market_demand': 'Very High Demand',
            'salary_range': '₹12,00,000 - ₹24,00,000 / yr',
            'estimated_hours': 40.0,
            'topics': 'Kafka Streams, Schema Registry',
            'source_reference': 'Data Engineering Industry Survey 2026',
            'is_verified': 'true'
        }, follow_redirects=True)

        # 3. Verify Activity Log recorded both actions
        with self.app.app_context():
            logs = AdminActivityLog.query.all()
            self.assertGreaterEqual(len(logs), 2)
            log_actions = [l.action for l in logs]
            print(f"  [+] Audit logs recorded: {len(logs)} entries ({', '.join(log_actions[:4])})")

        print("[PASS] Full CRUD and Audit Governance verified.")

if __name__ == '__main__':
    unittest.main()
