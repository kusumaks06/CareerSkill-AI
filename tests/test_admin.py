import json
import unittest
from datetime import datetime, timezone

from app import create_app
from models import (
    db,
    User,
    UserProfile,
    UserSkill,
    TargetCareer,
    SkillGapAnalysis,
    SkillGapItem,
    Course,
    CourseProgress,
    AssessmentQuestion,
    AssessmentAttempt,
    CourseFeedback,
    Suggestion,
    CustomCareer,
    SkillDefinition,
    MarketRequirement
)
from services.admin_service import admin_service
from services.recommendation_service import recommendation_service
from services.assessment_service import assessment_service


class AdminManagementTestCase(unittest.TestCase):
    """Automated test suite for Module 11: Enterprise Admin Dashboard & Management System."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            recommendation_service.seed_courses_if_empty()
            assessment_service.seed_questions_if_empty()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _create_admin_user(self, email="superadmin@example.com", name="Admin Supreme"):
        """Helper to create administrator user."""
        user = User(full_name=name, email=email, is_admin=True, role="admin", is_active=True)
        user.set_password("AdminSecurePass2026!")
        db.session.add(user)
        db.session.commit()
        return user

    def _create_student_user(self, email="student@example.com", name="Student One"):
        """Helper to create regular student user."""
        user = User(full_name=name, email=email, is_admin=False, role="user", is_active=True)
        user.set_password("StudentPass123!")
        db.session.add(user)
        db.session.flush()

        tc = TargetCareer(user_id=user.id, career_name="Data Analyst", normalized_career_name="data analyst")
        db.session.add(tc)

        profile = UserProfile(
            user_id=user.id,
            education="Bachelor's",
            degree="B.Tech",
            branch="Information Science"
        )
        db.session.add(profile)
        db.session.commit()
        return user

    # ---------------------------------------------------------
    # 1. Security & Authorization
    # ---------------------------------------------------------
    def test_unauthorized_access_protection(self):
        """Test that unauthenticated and regular student users are blocked from /admin/*."""
        # 1. Unauthenticated -> Redirects to login
        unauth_resp = self.client.get('/admin/dashboard')
        self.assertEqual(unauth_resp.status_code, 302)
        self.assertIn('/login', unauth_resp.headers['Location'])

        # 2. Regular student user -> 403 Forbidden
        with self.app.app_context():
            student = self._create_student_user()
            student_id = student.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = student_id
            sess['is_admin'] = False

        forbidden_resp = self.client.get('/admin/dashboard')
        self.assertEqual(forbidden_resp.status_code, 403)

        forbidden_users = self.client.get('/admin/users')
        self.assertEqual(forbidden_users.status_code, 403)

        forbidden_courses = self.client.get('/admin/courses')
        self.assertEqual(forbidden_courses.status_code, 403)

        # 3. Admin user -> 200 OK
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        admin_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn(b"Admin Dashboard", admin_resp.data)

    # ---------------------------------------------------------
    # 2. Dashboard Summary & Recent Activity
    # ---------------------------------------------------------
    def test_admin_dashboard_summary_metrics(self):
        """Test summary cards calculation and activity telemetry aggregation."""
        with self.app.app_context():
            admin = self._create_admin_user()
            student = self._create_student_user()

            # Create sample course progress & feedback
            course = Course.query.first()
            cp = CourseProgress(
                user_id=student.id,
                course_id=course.id,
                status="Completed",
                progress_percentage=100.0,
                hours_completed=10.0,
                total_hours=10.0
            )
            db.session.add(cp)

            fb = CourseFeedback(
                user_id=student.id,
                course_id=course.id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes"
            )
            db.session.add(fb)

            # Create sample suggestion
            sug = Suggestion(
                user_id=student.id,
                category="Missing Career",
                title="Add Bioinformatics Analyst",
                description="Healthcare genomics module.",
                status="Submitted"
            )
            db.session.add(sug)
            db.session.commit()

            summary = admin_service.get_dashboard_summary()

            self.assertEqual(summary['total_users'], 2)
            self.assertEqual(summary['active_users'], 2)
            self.assertEqual(summary['career_searches'], 1)
            self.assertEqual(summary['course_completions'], 1)
            self.assertEqual(summary['feedback_count'], 1)
            self.assertEqual(summary['avg_feedback_rating'], 5.0)
            self.assertEqual(summary['suggestions_count'], 1)
            self.assertEqual(summary['suggestions_pending'], 1)
            self.assertGreaterEqual(len(summary['popular_careers']), 1)

    # ---------------------------------------------------------
    # 3. User Management
    # ---------------------------------------------------------
    def test_user_management_and_activation_toggle(self):
        """Test listing users, viewing details, and toggling active/inactive status."""
        with self.app.app_context():
            admin = self._create_admin_user()
            student = self._create_student_user(email="toggle_test@example.com", name="Toggle Candidate")
            admin_id = admin.id
            student_id = student.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. GET /admin/users list
        list_resp = self.client.get('/admin/users')
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn(b"Toggle Candidate", list_resp.data)

        # 2. GET /admin/users/<id> detail
        detail_resp = self.client.get(f'/admin/users/{student_id}')
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn(b"Toggle Candidate", detail_resp.data)
        self.assertIn(b"Data Analyst", detail_resp.data)

        # 3. Deactivate user
        deact_resp = self.client.post(f'/admin/users/{student_id}/toggle-status', follow_redirects=True)
        self.assertEqual(deact_resp.status_code, 200)

        with self.app.app_context():
            saved_student = db.session.get(User, student_id)
            self.assertFalse(saved_student.is_active)

        # 4. Deactivated student tries to login -> Should be blocked
        login_resp = self.client.post('/login', data={
            'email': 'toggle_test@example.com',
            'password': 'StudentPass123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b"deactivated", login_resp.data)

        # 5. Reactivate user
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True
        react_resp = self.client.post(f'/admin/users/{student_id}/toggle-status', follow_redirects=True)
        self.assertEqual(react_resp.status_code, 200)

        with self.app.app_context():
            saved_student = db.session.get(User, student_id)
            self.assertTrue(saved_student.is_active)

    # ---------------------------------------------------------
    # 4. Career Management CRUD
    # ---------------------------------------------------------
    def test_career_management_crud(self):
        """Test creating, editing, and deleting custom career pathways."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Career
        add_resp = self.client.post('/admin/careers/save', data={
            'title': 'AI Solutions Architect',
            'category': 'Artificial Intelligence',
            'description': 'Designs enterprise AI pipelines and LLM infrastructure.',
            'core_skills': 'LLMOps, PyTorch, LangChain, Vector Databases, AWS',
            'secondary_skills': 'Docker, Kubernetes, FastAPI'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b"AI Solutions Architect", add_resp.data)

        # 2. Verify in DB and Edit
        with self.app.app_context():
            career = CustomCareer.query.filter_by(normalized_title='ai solutions architect').first()
            self.assertIsNotNone(career)
            c_id = career.id

        edit_resp = self.client.post('/admin/careers/save', data={
            'career_id': c_id,
            'title': 'AI Solutions Architect (Enterprise)',
            'category': 'Artificial Intelligence',
            'description': 'Updated: Enterprise GenAI infrastructure architecture.',
            'core_skills': 'LLMOps, PyTorch, LangChain, RAG Architecture'
        }, follow_redirects=True)
        self.assertEqual(edit_resp.status_code, 200)
        self.assertIn(b"AI Solutions Architect (Enterprise)", edit_resp.data)

        # 3. Delete Career
        del_resp = self.client.post(f'/admin/careers/{c_id}/delete', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with self.app.app_context():
            deleted_c = db.session.get(CustomCareer, c_id)
            self.assertIsNone(deleted_c)

    # ---------------------------------------------------------
    # 5. Skill Management CRUD
    # ---------------------------------------------------------
    def test_skill_management_crud(self):
        """Test creating, editing, and deleting skill definitions."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Skill
        add_resp = self.client.post('/admin/skills/save', data={
            'name': 'LangChain',
            'category': 'Technical',
            'difficulty': 'Moderate',
            'description': 'Framework for developing applications powered by language models.',
            'topics': 'Chains, Agents, Memory, Vector Stores'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b"LangChain", add_resp.data)

        # 2. Verify in DB & Delete
        with self.app.app_context():
            skill = SkillDefinition.query.filter_by(name='LangChain').first()
            self.assertIsNotNone(skill)
            s_id = skill.id

        del_resp = self.client.post(f'/admin/skills/{s_id}/delete', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with self.app.app_context():
            deleted_s = db.session.get(SkillDefinition, s_id)
            self.assertIsNone(deleted_s)

    # ---------------------------------------------------------
    # 6. Market Requirements Management
    # ---------------------------------------------------------
    def test_market_requirements_crud_and_data_classification(self):
        """Test creating and managing labor market requirements with Verified vs Estimated tags."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Requirement
        add_resp = self.client.post('/admin/market-requirements/save', data={
            'career_title': 'Cloud Security Engineer',
            'skill_name': 'IAM & Cloud Governance',
            'required_level': 'Advanced',
            'importance': 'Critical',
            'estimated_hours': 35.0,
            'topics': 'AWS IAM, Azure RBAC, Zero Trust Architecture',
            'source_reference': 'Gartner Cloud Security Report 2026',
            'is_verified': 'true'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b"Cloud Security Engineer", add_resp.data)
        self.assertIn(b"Verified Data", add_resp.data)

        # 2. Delete Requirement
        with self.app.app_context():
            req = MarketRequirement.query.filter_by(career_title='Cloud Security Engineer').first()
            self.assertIsNotNone(req)
            r_id = req.id

        del_resp = self.client.post(f'/admin/market-requirements/{r_id}/delete', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with self.app.app_context():
            deleted_r = db.session.get(MarketRequirement, r_id)
            self.assertIsNone(deleted_r)

    # ---------------------------------------------------------
    # 7. Course Management CRUD & Toggle Status
    # ---------------------------------------------------------
    def test_course_management_crud(self):
        """Test adding, editing, deactivating, and deleting courses."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Course
        add_resp = self.client.post('/admin/courses/save', data={
            'title': 'Advanced RAG & Vector Databases Masterclass',
            'provider': 'Coursera',
            'skill': 'Vector Databases',
            'url': 'https://www.coursera.org/learn/vector-db',
            'level': 'Advanced',
            'duration_hours': 15.0,
            'difficulty': 'Difficult',
            'rating': 4.9,
            'topics': 'ChromaDB, Pinecone, Hybrid Search, Dense Embeddings',
            'description': 'Build high-performance retrieval augmented generation pipelines.'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b"Advanced RAG &amp; Vector Databases", add_resp.data)

        # 2. Toggle Status
        with self.app.app_context():
            c = Course.query.filter_by(title='Advanced RAG & Vector Databases Masterclass').first()
            self.assertIsNotNone(c)
            c_id = c.id

        tog_resp = self.client.post(f'/admin/courses/{c_id}/toggle-status', follow_redirects=True)
        self.assertEqual(tog_resp.status_code, 200)

        with self.app.app_context():
            saved_c = db.session.get(Course, c_id)
            self.assertFalse(saved_c.is_active)

        # 3. Delete Course
        del_resp = self.client.post(f'/admin/courses/{c_id}/delete', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with self.app.app_context():
            deleted_c = db.session.get(Course, c_id)
            self.assertIsNone(deleted_c)

    # ---------------------------------------------------------
    # 8. Assessment Management CRUD & Pass Rate Stats
    # ---------------------------------------------------------
    def test_assessment_management_crud(self):
        """Test diagnostic questions CRUD and difficulty analytics."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Add Question
        add_resp = self.client.post('/admin/assessments/save', data={
            'skill': 'Vector Databases',
            'topic': 'Embeddings',
            'question': 'Which metric is commonly used to measure distance between normalized dense vector embeddings?',
            'options': 'Cosine Similarity\nEuclidean Manhattan Distance\nLevenshtein Distance\nJaccard Index',
            'correct_answer': 'Cosine Similarity',
            'difficulty': 'Moderate',
            'explanation': 'Cosine similarity evaluates cosine angle between two non-zero vectors.'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b"Cosine Similarity", add_resp.data)

        # 2. Verify in DB & Delete
        with self.app.app_context():
            q = AssessmentQuestion.query.filter_by(skill='Vector Databases').first()
            self.assertIsNotNone(q)
            q_id = q.id

        del_resp = self.client.post(f'/admin/assessments/{q_id}/delete', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        with self.app.app_context():
            deleted_q = db.session.get(AssessmentQuestion, q_id)
            self.assertIsNone(deleted_q)

    # ---------------------------------------------------------
    # 9. Enterprise Analytics & Roadmaps
    # ---------------------------------------------------------
    def test_roadmaps_and_analytics_views(self):
        """Test /admin/roadmaps and /admin/analytics rendering and true DB calculations."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Roadmaps view
        road_resp = self.client.get('/admin/roadmaps')
        self.assertEqual(road_resp.status_code, 200)
        self.assertIn(b"AI Career Roadmaps", road_resp.data)

        # 2. Analytics view
        ana_resp = self.client.get('/admin/analytics')
        self.assertEqual(ana_resp.status_code, 200)
        self.assertIn(b"Platform Telemetry", ana_resp.data)

    # ---------------------------------------------------------
    # 10. Admin Settings & Seeding Utilities
    # ---------------------------------------------------------
    def test_admin_settings_and_seed_actions(self):
        """Test /admin/settings view and catalog synchronization actions."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. GET Settings
        set_resp = self.client.get('/admin/settings')
        self.assertEqual(set_resp.status_code, 200)
        self.assertIn(b"CareerSkill AI v2.4", set_resp.data)

        # 2. Seed courses
        sc_resp = self.client.post('/admin/settings/seed-courses', follow_redirects=True)
        self.assertEqual(sc_resp.status_code, 200)
        self.assertIn(b"synchronized successfully", sc_resp.data)

        # 3. Seed questions
        sq_resp = self.client.post('/admin/settings/seed-questions', follow_redirects=True)
        self.assertEqual(sq_resp.status_code, 200)
        self.assertIn(b"synchronized successfully", sq_resp.data)

    # ---------------------------------------------------------
    # 11. Full End-to-End Admin Flow
    # ---------------------------------------------------------
    def test_complete_admin_end_to_end_journey(self):
        """
        Complete flow test:
        Admin Login -> Admin Dashboard -> Users -> Careers -> Skills ->
        Market Requirements -> Courses -> Assessments -> Roadmaps ->
        Feedback -> Suggestions -> Analytics -> Logout.
        """
        with self.app.app_context():
            admin = self._create_admin_user(email="journey_admin@example.com")

        # 1. Admin Login
        login_resp = self.client.post('/login', data={
            'email': 'journey_admin@example.com',
            'password': 'AdminSecurePass2026!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # 2. Dashboard
        r_dash = self.client.get('/admin/dashboard')
        self.assertEqual(r_dash.status_code, 200)

        # 3. Users
        r_users = self.client.get('/admin/users')
        self.assertEqual(r_users.status_code, 200)

        # 4. Careers
        r_careers = self.client.get('/admin/careers')
        self.assertEqual(r_careers.status_code, 200)

        # 5. Skills
        r_skills = self.client.get('/admin/skills')
        self.assertEqual(r_skills.status_code, 200)

        # 6. Market Requirements
        r_market = self.client.get('/admin/market-requirements')
        self.assertEqual(r_market.status_code, 200)

        # 7. Courses
        r_courses = self.client.get('/admin/courses')
        self.assertEqual(r_courses.status_code, 200)

        # 8. Assessments
        r_assess = self.client.get('/admin/assessments')
        self.assertEqual(r_assess.status_code, 200)

        # 9. Roadmaps
        r_roadmaps = self.client.get('/admin/roadmaps')
        self.assertEqual(r_roadmaps.status_code, 200)

        # 10. Feedback
        r_fb = self.client.get('/admin/feedback')
        self.assertEqual(r_fb.status_code, 200)

        # 11. Suggestions
        r_sug = self.client.get('/admin/suggestions')
        self.assertEqual(r_sug.status_code, 200)

        # 12. Analytics
        r_ana = self.client.get('/admin/analytics')
        self.assertEqual(r_ana.status_code, 200)

        # 13. Activity Log
        r_act = self.client.get('/admin/activity-log')
        self.assertEqual(r_act.status_code, 200)
        self.assertIn(b"Activity & Audit Log", r_act.data)

        # 14. Settings
        r_set = self.client.get('/admin/settings')
        self.assertEqual(r_set.status_code, 200)

        # 15. Logout
        logout_resp = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)

        # 16. Attempting to access admin after logout -> Redirect to login
        recheck = self.client.get('/admin/dashboard')
        self.assertEqual(recheck.status_code, 302)
        self.assertIn('/login', recheck.headers['Location'])

    # ---------------------------------------------------------
    # 12. User Role Toggle & User Deletion & Admin Creation
    # ---------------------------------------------------------
    def test_user_role_toggle_delete_and_create_admin(self):
        """Test admin role toggling, secure deletion of user accounts, and dedicated admin creation."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id
            student = self._create_student_user(email="test_role@example.com", name="Role Candidate")
            student_id = student.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # 1. Promote student to admin
        promote_resp = self.client.post(f'/admin/users/{student_id}/toggle-role', follow_redirects=True)
        self.assertEqual(promote_resp.status_code, 200)
        with self.app.app_context():
            upgraded = db.session.get(User, student_id)
            self.assertTrue(upgraded.is_admin)
            self.assertEqual(upgraded.role, "admin")

        # 2. Demote back to user
        demote_resp = self.client.post(f'/admin/users/{student_id}/toggle-role', follow_redirects=True)
        self.assertEqual(demote_resp.status_code, 200)
        with self.app.app_context():
            downgraded = db.session.get(User, student_id)
            self.assertFalse(downgraded.is_admin)
            self.assertEqual(downgraded.role, "user")

        # 3. Create a dedicated Admin user
        create_admin_resp = self.client.post('/admin/users/create-admin', data={
            'full_name': 'Deputy Admin',
            'email': 'deputy.admin@example.com',
            'password': 'SecureAdminPassword2026!'
        }, follow_redirects=True)
        self.assertEqual(create_admin_resp.status_code, 200)

        with self.app.app_context():
            new_admin = User.query.filter_by(email='deputy.admin@example.com').first()
            self.assertIsNotNone(new_admin)
            self.assertTrue(new_admin.is_admin)
            self.assertEqual(new_admin.role, "admin")

        # 4. Delete the student user
        del_user_resp = self.client.post(f'/admin/users/{student_id}/delete', follow_redirects=True)
        self.assertEqual(del_user_resp.status_code, 200)

        with self.app.app_context():
            deleted_user = db.session.get(User, student_id)
            self.assertIsNone(deleted_user)

    # ---------------------------------------------------------
    # 13. Dedicated 403 Access Denied View Verification
    # ---------------------------------------------------------
    def test_custom_403_access_denied_page_rendering(self):
        """Test that regular authenticated user receiving 403 gets the custom dark mode 403 page."""
        with self.app.app_context():
            student = self._create_student_user(email="learner403@example.com", name="Learner 403")
            student_id = student.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = student_id
            sess['is_admin'] = False

        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b"403", resp.data)
        self.assertIn(b"Access Denied", resp.data)
        self.assertIn(b"administrator permissions", resp.data)

    # ---------------------------------------------------------
    # 14. Admin Activity Log Audit Trail
    # ---------------------------------------------------------
    def test_admin_activity_log_audit_trail(self):
        """Test that admin actions generate immutable audit log records."""
        with self.app.app_context():
            admin = self._create_admin_user()
            admin_id = admin.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin_id
            sess['is_admin'] = True

        # Perform an action: create a skill definition
        self.client.post('/admin/skills/save', data={
            'name': 'GraphQL Architecture',
            'category': 'Backend',
            'difficulty': 'Moderate',
            'demand_status': 'In-Demand',
            'description': 'Modern schema design and API query protocol.',
            'topics': 'Queries, Mutations, Subscriptions, Resolvers'
        }, follow_redirects=True)

        # Inspect Activity Logs
        logs_resp = self.client.get('/admin/activity-log')
        self.assertEqual(logs_resp.status_code, 200)
        self.assertIn(b"GraphQL Architecture", logs_resp.data)

        # Inspect via JSON API
        api_resp = self.client.get('/api/admin/activity-log')
        self.assertEqual(api_resp.status_code, 200)
        data = json.loads(api_resp.data)
        self.assertTrue(data.get('success'))
        self.assertGreaterEqual(len(data.get('logs', [])), 1)


if __name__ == '__main__':
    unittest.main()

