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
    Suggestion,
    LearningActivity
)
from services.suggestion_service import suggestion_service
from services.recommendation_service import recommendation_service
from services.assessment_service import assessment_service


class UserSuggestionsTestCase(unittest.TestCase):
    """Automated test suite for Module 10: User Suggestions & Improvement System."""

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

    def _create_test_user(self, email="test_innovator@example.com", name="Morgan Innovator"):
        """Helper to create candidate user."""
        user = User(full_name=name, email=email)
        user.set_password("SecurePass123!")
        db.session.add(user)
        db.session.flush()

        tc = TargetCareer(
            user_id=user.id,
            career_name="Data Analyst",
            normalized_career_name="Data Analyst"
        )
        db.session.add(tc)

        profile = UserProfile(
            user_id=user.id,
            education="Bachelor's",
            degree="B.Tech",
            branch="Computer Science",
            learning_hours_per_week=10.0
        )
        db.session.add(profile)
        db.session.commit()
        return user

    def test_suggestion_model_creation_and_relationships(self):
        """Test Suggestion model attributes, relationships, and to_dict method."""
        with self.app.app_context():
            user = self._create_test_user()

            suggestion = Suggestion(
                user_id=user.id,
                category="Missing Career",
                title="Add Healthcare Data Analyst",
                description="Include healthcare analytics, EHR standards, and HIPAA compliance.",
                career="Healthcare Data Analyst",
                skill="EHR Analytics",
                course="Coursera Health Informatics",
                status="Submitted"
            )
            db.session.add(suggestion)
            db.session.commit()

            # Verify saved model
            saved = db.session.get(Suggestion, suggestion.id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.category, "Missing Career")
            self.assertEqual(saved.title, "Add Healthcare Data Analyst")
            self.assertEqual(saved.career, "Healthcare Data Analyst")
            self.assertEqual(saved.status, "Submitted")
            self.assertIsNone(saved.admin_response)

            # Check User relationship
            self.assertEqual(len(user.suggestions), 1)
            self.assertEqual(user.suggestions[0].id, saved.id)

            # Check to_dict()
            d = saved.to_dict()
            self.assertEqual(d['id'], saved.id)
            self.assertEqual(d['user_name'], "Morgan Innovator")
            self.assertEqual(d['category'], "Missing Career")
            self.assertTrue(d['is_editable'])
            self.assertFalse(d['has_response'])
            self.assertIn("Suggestion", repr(saved))

    def test_submit_suggestion_service_and_activity_logging(self):
        """Test suggestion_service.submit_suggestion records suggestion and logs learning activity."""
        with self.app.app_context():
            user = self._create_test_user()

            result = suggestion_service.submit_suggestion(
                user_id=user.id,
                category="Missing Skill",
                title="Add dbt (data build tool)",
                description="Modern data stack needs dbt transformation module.",
                skill="dbt"
            )

            self.assertTrue(result['success'])
            self.assertEqual(result['suggestion']['status'], 'Submitted')
            self.assertEqual(result['suggestion']['skill'], 'dbt')

            # Verify Learning Activity logged
            activities = LearningActivity.query.filter_by(user_id=user.id, activity_type='Suggestion').all()
            self.assertEqual(len(activities), 1)
            self.assertIn("dbt", activities[0].title)

    def test_user_can_edit_and_delete_only_when_submitted(self):
        """Test edit and delete rules based on status 'Submitted' vs locked statuses."""
        with self.app.app_context():
            user = self._create_test_user()

            # 1. Submit suggestion
            res = suggestion_service.submit_suggestion(
                user_id=user.id,
                category="Roadmap Suggestion",
                title="Include Git workflow in Phase 1",
                description="Git version control should be in the initial foundational phase."
            )
            s_id = res['suggestion']['id']

            # 2. Edit while status == 'Submitted' -> Should succeed
            edit_res = suggestion_service.update_user_suggestion(
                suggestion_id=s_id,
                user_id=user.id,
                title="Include Git & GitHub workflow in Phase 1",
                description="Updated: Foundational version control is critical."
            )
            self.assertTrue(edit_res['success'])
            self.assertEqual(edit_res['suggestion']['title'], "Include Git & GitHub workflow in Phase 1")

            # 3. Admin changes status to 'Under Review'
            suggestion_service.admin_update_suggestion(
                suggestion_id=s_id,
                status="Under Review",
                admin_response="We are reviewing this with our curriculum committee."
            )

            # 4. User tries to edit while status == 'Under Review' -> Should FAIL
            edit_fail = suggestion_service.update_user_suggestion(
                suggestion_id=s_id,
                user_id=user.id,
                title="Attempted change",
                description="Should not allow"
            )
            self.assertFalse(edit_fail['success'])
            self.assertIn("cannot be modified", edit_fail['error'])

            # 5. User tries to delete while status == 'Under Review' -> Should FAIL
            del_fail = suggestion_service.delete_user_suggestion(
                suggestion_id=s_id,
                user_id=user.id
            )
            self.assertFalse(del_fail['success'])
            self.assertIn("cannot be deleted", del_fail['error'])

            # 6. Admin reverts status back to 'Submitted' -> Delete should now succeed
            suggestion_service.admin_update_suggestion(suggestion_id=s_id, status="Submitted")
            del_ok = suggestion_service.delete_user_suggestion(suggestion_id=s_id, user_id=user.id)
            self.assertTrue(del_ok['success'])

            # Verify deleted from DB
            deleted_s = db.session.get(Suggestion, s_id)
            self.assertIsNone(deleted_s)

    def test_admin_filtering_and_analytics_aggregation(self):
        """Test admin filtering by category, status, keyword, and aggregate metrics calculation."""
        with self.app.app_context():
            u1 = self._create_test_user(email="user1@example.com", name="Alex One")
            u2 = self._create_test_user(email="user2@example.com", name="Blake Two")

            # Submit 3 diverse suggestions
            s1 = suggestion_service.submit_suggestion(
                user_id=u1.id,
                category="Missing Career",
                title="AI Ethics Specialist",
                description="Add ethical AI pathway.",
                career="AI Ethics Specialist"
            )['suggestion']

            s2 = suggestion_service.submit_suggestion(
                user_id=u2.id,
                category="Incorrect Recommendation",
                title="Outdated Python 2 course",
                description="Course link refers to deprecated version.",
                course="Python 2 Fundamentals"
            )['suggestion']

            s3 = suggestion_service.submit_suggestion(
                user_id=u1.id,
                category="Missing Career",
                title="Healthcare Data Analyst",
                description="Hospital analytics track.",
                career="Healthcare Data Analyst"
            )['suggestion']

            # Admin responds and resolves s2
            suggestion_service.admin_update_suggestion(
                suggestion_id=s2['id'],
                status="Resolved",
                admin_response="Updated course link to Python 3.12 version. Thank you!"
            )

            # Admin marks s3 as 'Under Review'
            suggestion_service.admin_update_suggestion(
                suggestion_id=s3['id'],
                status="Under Review",
                admin_response="Analyzing labor market demand data."
            )

            # Test analytics
            analytics = suggestion_service.get_suggestion_analytics()
            self.assertEqual(analytics['total_suggestions'], 3)
            self.assertEqual(analytics['new_count'], 1)
            self.assertEqual(analytics['under_review_count'], 1)
            self.assertEqual(analytics['resolved_count'], 1)
            self.assertEqual(analytics['category_counts']['Missing Career'], 2)
            self.assertEqual(len(analytics['top_requested_careers']), 2)
            self.assertEqual(len(analytics['top_reported_courses']), 1)

            # Test admin filters
            by_status = suggestion_service.get_all_suggestions_for_admin(status="Resolved")
            self.assertEqual(len(by_status), 1)
            self.assertEqual(by_status[0]['id'], s2['id'])

            by_cat = suggestion_service.get_all_suggestions_for_admin(category="Missing Career")
            self.assertEqual(len(by_cat), 2)

            by_search = suggestion_service.get_all_suggestions_for_admin(search_query="deprecated")
            self.assertEqual(len(by_search), 1)
            self.assertEqual(by_search[0]['title'], "Outdated Python 2 course")

    def test_suggestions_web_routes_and_dashboard_widget(self):
        """Test GET /suggestions, POST /suggestions, and dashboard widget rendering."""
        with self.app.app_context():
            user = self._create_test_user()
            user_id = user.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        # 1. GET /suggestions page
        get_resp = self.client.get('/suggestions')
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn(b"Suggestions &", get_resp.data)
        self.assertIn(b"Missing Career", get_resp.data)

        # 2. POST /suggestions
        post_resp = self.client.post('/suggestions', data={
            'category': 'Missing Career',
            'title': 'Cloud Security Architect',
            'description': 'Please add AWS and Azure cloud security specialization.',
            'career': 'Cloud Security Architect',
            'skill': 'Cloud Security',
            'course': ''
        }, follow_redirects=True)
        self.assertEqual(post_resp.status_code, 200)
        self.assertIn(b"submitted successfully", post_resp.data)
        self.assertIn(b"Cloud Security Architect", post_resp.data)

        # 3. GET /dashboard and verify suggestions section appears
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b"My Suggestions & Platform Feedback", dash_resp.data)
        self.assertIn(b"Cloud Security Architect", dash_resp.data)

    def test_admin_suggestions_page_and_response_action(self):
        """Test GET /admin/suggestions, POST /admin/suggestions/<id>/respond."""
        with self.app.app_context():
            user = self._create_test_user()
            res = suggestion_service.submit_suggestion(
                user_id=user.id,
                category="General Suggestion",
                title="Add Dark Mode Toggle shortcut",
                description="A quick keyboard shortcut for theme toggling would be great."
            )
            s_id = res['suggestion']['id']

        # 1. GET Admin Suggestions HTML
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['is_admin'] = True
        admin_resp = self.client.get('/admin/suggestions')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn(b"User Suggestions &", admin_resp.data)
        self.assertIn(b"Add Dark Mode Toggle shortcut", admin_resp.data)

        # 2. Admin Posts Response & Marks Resolved
        respond_resp = self.client.post(f'/admin/suggestions/{s_id}/respond', data={
            'status': 'Resolved',
            'admin_response': 'Feature approved and implemented. Press Ctrl+Shift+D to toggle!'
        }, follow_redirects=True)
        self.assertEqual(respond_resp.status_code, 200)
        self.assertIn(b"updated to", respond_resp.data)
        self.assertIn(b"Resolved", respond_resp.data)

        # 3. Verify in DB
        with self.app.app_context():
            saved_s = db.session.get(Suggestion, s_id)
            self.assertEqual(saved_s.status, 'Resolved')
            self.assertEqual(saved_s.admin_response, 'Feature approved and implemented. Press Ctrl+Shift+D to toggle!')
            self.assertIsNotNone(saved_s.resolved_at)

    def test_ajax_suggestion_endpoints(self):
        """Test /api/suggestions and /api/admin/suggestions endpoints."""
        with self.app.app_context():
            user = self._create_test_user()
            user_id = user.id

        # 1. User AJAX POST
        post_resp = self.client.post('/api/suggestions', json={
            'user_id': user_id,
            'category': 'Missing Skill',
            'title': 'Add Kubernetes Orchestration',
            'description': 'DevOps roadmap needs K8s hands-on projects.',
            'skill': 'Kubernetes'
        })
        self.assertEqual(post_resp.status_code, 200)
        p_data = json.loads(post_resp.data)
        self.assertTrue(p_data['success'])
        s_id = p_data['suggestion']['id']

        # 2. User AJAX GET
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = False
        get_resp = self.client.get('/api/suggestions')
        self.assertEqual(get_resp.status_code, 200)
        g_data = json.loads(get_resp.data)
        self.assertTrue(g_data['success'])
        self.assertEqual(len(g_data['suggestions']), 1)

        # 3. Admin AJAX GET
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = True
        admin_get = self.client.get('/api/admin/suggestions')
        self.assertEqual(admin_get.status_code, 200)
        ag_data = json.loads(admin_get.data)
        self.assertTrue(ag_data['success'])
        self.assertGreaterEqual(ag_data['analytics']['total_suggestions'], 1)

        # 4. Admin AJAX Update
        admin_update = self.client.post(f'/api/admin/suggestions/{s_id}/update', json={
            'status': 'Under Review',
            'admin_response': 'Reviewing with DevOps module team.'
        })
        self.assertEqual(admin_update.status_code, 200)
        au_data = json.loads(admin_update.data)
        self.assertTrue(au_data['success'])
        self.assertEqual(au_data['suggestion']['status'], 'Under Review')

    def test_security_and_unauthorized_isolation(self):
        """Test that unauthorized users cannot edit/delete another user's suggestions."""
        with self.app.app_context():
            u1 = self._create_test_user(email="victim@example.com", name="Victim User")
            u2 = self._create_test_user(email="attacker@example.com", name="Attacker User")

            res = suggestion_service.submit_suggestion(
                user_id=u1.id,
                category="General Suggestion",
                title="Victim suggestion",
                description="Victim details"
            )
            s_id = res['suggestion']['id']

            # Attacker tries to edit u1's suggestion
            attacker_edit = suggestion_service.update_user_suggestion(
                suggestion_id=s_id,
                user_id=u2.id,
                title="Hacked title",
                description="Hacked desc"
            )
            self.assertFalse(attacker_edit['success'])
            self.assertIn("access denied", attacker_edit['error'])

            # Attacker tries to delete u1's suggestion
            attacker_del = suggestion_service.delete_user_suggestion(
                suggestion_id=s_id,
                user_id=u2.id
            )
            self.assertFalse(attacker_del['success'])
            self.assertIn("access denied", attacker_del['error'])

            # Verify suggestion was NOT modified or deleted
            saved = db.session.get(Suggestion, s_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.title, "Victim suggestion")

    def test_full_module10_user_and_admin_flow(self):
        """
        Complete end-to-end flow test:
        User Login -> Dashboard -> Suggestions -> Submit Suggestion -> View Suggestion ->
        Admin Dashboard -> View Suggestion -> Add Response -> Change Status ->
        User sees updated status & response on Dashboard and Suggestions History.
        """
        with self.app.app_context():
            user = self._create_test_user(email="journey10@example.com", name="Jordan Creator")
            user_id = user.id

        # 1. User Login
        login_resp = self.client.post('/login', data={
            'email': 'journey10@example.com',
            'password': 'SecurePass123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # 2. User navigates to /suggestions and submits
        sub_resp = self.client.post('/suggestions', data={
            'category': 'Missing Career',
            'title': 'Quantum Computing Software Developer',
            'description': 'Add roadmap for Qiskit and quantum circuit simulation.',
            'career': 'Quantum Computing Software Developer',
            'skill': 'Qiskit'
        }, follow_redirects=True)
        self.assertEqual(sub_resp.status_code, 200)
        self.assertIn(b"Quantum Computing Software Developer", sub_resp.data)

        # 3. Admin visits /admin/suggestions
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = True
        admin_resp = self.client.get('/admin/suggestions')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn(b"Jordan Creator", admin_resp.data)
        self.assertIn(b"Quantum Computing Software Developer", admin_resp.data)

        # 4. Admin responds and resolves
        with self.app.app_context():
            s = Suggestion.query.filter_by(user_id=user_id).first()
            s_id = s.id

        admin_act = self.client.post(f'/admin/suggestions/{s_id}/respond', data={
            'status': 'Resolved',
            'admin_response': 'Exciting addition! We have scheduled a Quantum Computing module for Q4 roadmap.'
        }, follow_redirects=True)
        self.assertEqual(admin_act.status_code, 200)

        # 5. User checks /dashboard -> Sees resolved status & response
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = False
        user_dash = self.client.get('/dashboard')
        self.assertEqual(user_dash.status_code, 200)
        self.assertIn(b"Resolved", user_dash.data)
        self.assertIn(b"Quantum Computing", user_dash.data)

        # 6. User checks /suggestions history -> Sees complete admin response
        user_hist = self.client.get('/suggestions')
        self.assertEqual(user_hist.status_code, 200)
        self.assertIn(b"Exciting addition! We have scheduled a Quantum Computing module", user_hist.data)

    def test_unauthenticated_redirection_and_empty_inputs_validation(self):
        """Test unauthenticated access redirects and empty input fields return validation errors."""
        # 1. Unauthenticated GET /suggestions -> Redirect to login
        resp = self.client.get('/suggestions')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        # 2. Unauthenticated POST /api/suggestions -> 401
        api_resp = self.client.post('/api/suggestions', json={
            'title': 'No Auth Title',
            'description': 'No Auth Desc'
        })
        self.assertEqual(api_resp.status_code, 401)

        # 3. Empty title validation in service
        with self.app.app_context():
            user = self._create_test_user(email="val@example.com", name="Val User")
            res = suggestion_service.submit_suggestion(
                user_id=user.id,
                category="General Suggestion",
                title="   ",
                description="Some valid description"
            )
            self.assertFalse(res['success'])
            self.assertIn("title is required", res['error'])

            res2 = suggestion_service.submit_suggestion(
                user_id=user.id,
                category="General Suggestion",
                title="Valid Title",
                description="  "
            )
            self.assertFalse(res2['success'])
            self.assertIn("description is required", res2['error'])


if __name__ == '__main__':
    unittest.main()
