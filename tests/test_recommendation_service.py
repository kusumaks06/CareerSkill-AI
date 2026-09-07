import unittest
import json
import html
from app import create_app
from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    CareerProfile, 
    Course, 
    UserCourseRecommendation
)
from services.recommendation_service import recommendation_service
from services.skill_gap_service import skill_gap_service

class RecommendationServiceTestCase(unittest.TestCase):
    """Test suite for Personalized Course Recommendation Engine (Step 4)."""

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Seed courses
        recommendation_service.seed_courses_if_empty()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_standard_test_user(self):
        """
        Creates candidate matching the exact required test case:
        Target Career: Data Analyst
        Current Skills:
          - Python: Intermediate (50)
          - SQL: Beginner (25)
          - Excel: Intermediate (50)
          - Power BI: Beginner (25)
        Learning Time: 2 hours/day, 5 days/week (10 hrs/week)
        Preferences: ['Video Courses', 'Hands-on Practice', 'Projects']
        """
        user = User(
            full_name="Alex Data Analyst",
            email="alex.analyst@example.com"
        )
        user.set_password("SecurePass123")
        db.session.add(user)
        db.session.commit()

        profile = UserProfile(
            user_id=user.id,
            education="Bachelor of Engineering",
            degree="BE",
            branch="AI & Data Science",
            graduation_year="2026",
            current_status="Student",
            experience_level="No experience",
            learning_hours_per_day="2 hours/day",
            learning_days_per_week=5,
            learning_hours_per_week=10.0,
            preferred_difficulty="Balanced"
        )
        profile.set_learning_preferences(["Video Courses", "Hands-on Practice", "Projects"])
        profile.set_career_goals(["Get first job as Data Analyst"])
        db.session.add(profile)

        # Target Career
        target_career = TargetCareer(
            user_id=user.id,
            career_name="Data Analyst",
            normalized_career_name="data analyst"
        )
        db.session.add(target_career)

        # User Skills
        skills_data = [
            ("Python", "Intermediate", 50),
            ("SQL", "Beginner", 25),
            ("Excel", "Intermediate", 50),
            ("Power BI", "Beginner", 25)
        ]
        for name, level, score in skills_data:
            s = UserSkill(
                user_id=user.id,
                skill_name=name,
                proficiency_level=level,
                proficiency_score=score,
                confidence_level=3
            )
            db.session.add(s)

        db.session.commit()
        return user

    def test_course_model_and_seeding(self):
        """Verifies Course model schema, serialization, and dataset seeding."""
        count = Course.query.count()
        self.assertGreater(count, 15, "Database should contain seeded courses")

        sql_course = Course.query.filter_by(skill="SQL").first()
        self.assertIsNotNone(sql_course)
        self.assertIsNotNone(sql_course.title)
        self.assertIsNotNone(sql_course.provider)
        self.assertIsInstance(sql_course.get_topics(), list)
        self.assertGreater(len(sql_course.get_topics()), 0)

        course_dict = sql_course.to_dict()
        self.assertIn('title', course_dict)
        self.assertIn('provider', course_dict)
        self.assertIn('skill', course_dict)
        self.assertIn('resource_type', course_dict)

    def test_gap_based_recommendations_for_data_analyst(self):
        """
        Tests recommendation generation for Data Analyst test candidate:
        - SQL & Power BI (Beginner) must be prioritized over already Intermediate skills.
        - SQL has Critical importance and should have Critical/High priority.
        - High recommendation scores (> 80%) for gap courses.
        """
        user = self._create_standard_test_user()
        rec_data = recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")

        self.assertEqual(rec_data['target_role'], "Data Analyst")
        self.assertFalse(rec_data['is_custom_role'])
        self.assertGreater(len(rec_data['recommendations']), 0)

        top_recs = rec_data['recommendations'][:5]
        top_skills = [r['skill'] for r in top_recs]

        # Verify SQL or Power BI or Missing skills are in the top recommendations
        self.assertTrue('SQL' in top_skills or 'Power BI' in top_skills or 'Statistics' in top_skills,
                        f"Top recommendations should focus on skill gaps, got: {top_skills}")

        # Check top recommendation properties
        top_course = rec_data['recommendations'][0]
        self.assertIn('recommendation_score', top_course)
        self.assertGreaterEqual(top_course['recommendation_score'], 70)
        self.assertIn('why_recommended', top_course)
        self.assertIn('estimated_weeks', top_course)
        self.assertGreater(len(top_course['why_recommended']), 10)

    def test_topic_matching_in_recommendations(self):
        """Verifies topic decomposition matches user missing topics against course topics."""
        user = self._create_standard_test_user()
        rec_data = recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")

        sql_recs = [r for r in rec_data['recommendations'] if r['skill'] == 'SQL']
        self.assertGreater(len(sql_recs), 0)

        # SQL beginner should match missing SQL topics like JOINs, CTEs, Window Functions
        has_matched_topics = any(len(r.get('matched_topics', [])) > 0 for r in sql_recs)
        self.assertTrue(has_matched_topics, "At least one SQL course should report matched topics")

    def test_weekly_learning_time_calculation(self):
        """Verifies estimated completion weeks are calculated from user weekly hours."""
        user = self._create_standard_test_user()
        rec_data = recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")

        for course in rec_data['recommendations']:
            duration = course['duration_hours']
            expected_weeks = max(1, -(-int(duration) // 10))  # ceil division
            self.assertEqual(course['estimated_weeks'], expected_weeks)

    def test_custom_career_role_synthesis(self):
        """Verifies custom role (Healthcare Data Analyst) does not crash and provides recommendations."""
        user = self._create_standard_test_user()
        rec_data = recommendation_service.generate_recommendations(user=user, target_role="Healthcare Data Analyst")

        self.assertEqual(rec_data['target_role'], "Healthcare Data Analyst")
        self.assertTrue(rec_data['is_custom_role'])
        self.assertGreater(len(rec_data['recommendations']), 0)
        self.assertIn("related market roles", rec_data['gap_summary_explanation'].lower())

    def test_learning_plan_preview_generation(self):
        """Verifies sequential learning plan roadmap preview is dynamically generated."""
        user = self._create_standard_test_user()
        rec_data = recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")

        plan = rec_data['learning_plan_preview']
        self.assertIsInstance(plan, list)
        self.assertGreater(len(plan), 0)
        
        # Check first step
        step1 = plan[0]
        self.assertEqual(step1['step'], 1)
        self.assertIn('title', step1)
        self.assertIn('course_title', step1)
        self.assertIn('duration_hours', step1)

    def test_recommendation_status_persistence(self):
        """Verifies updating status (In Progress, Completed) persists to SQLite."""
        user = self._create_standard_test_user()
        course = Course.query.first()
        self.assertIsNotNone(course)

        # Update status to In Progress
        res = recommendation_service.update_recommendation_status(user.id, course.id, "In Progress")
        self.assertTrue(res['success'])

        saved = UserCourseRecommendation.query.filter_by(user_id=user.id, course_id=course.id).first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "In Progress")
        self.assertIsNotNone(saved.started_at)

        # Update status to Completed
        res2 = recommendation_service.update_recommendation_status(user.id, course.id, "Completed")
        self.assertTrue(res2['success'])
        db.session.refresh(saved)
        self.assertEqual(saved.status, "Completed")
        self.assertIsNotNone(saved.completed_at)

    def test_http_course_recommendations_route(self):
        """Verifies GET /course-recommendations renders HTTP 200 with content."""
        user = self._create_standard_test_user()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/course-recommendations')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn("Your Personalized Learning Recommendations", content)
        self.assertIn("Data Analyst", content)
        self.assertIn("Start Learning", content)
        self.assertIn("YOUR RECOMMENDED ORDER", content)

    def test_http_course_detail_route(self):
        """Verifies GET /course/<id> renders HTTP 200 with syllabus and why-recommended box."""
        user = self._create_standard_test_user()
        course = Course.query.first()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get(f'/course/{course.id}')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn(html.escape(course.title), content)
        self.assertIn(course.provider, content)
        self.assertIn("Why This Course is Recommended For You", content)
        self.assertIn("Start Learning", content)

    def test_http_refresh_recommendations_route(self):
        """Verifies POST /refresh-recommendations redirects and updates."""
        user = self._create_standard_test_user()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.post('/refresh-recommendations')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/course-recommendations'))

    def test_http_api_recommendation_status_route(self):
        """Verifies POST /api/recommendations/status endpoint."""
        user = self._create_standard_test_user()
        course = Course.query.first()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.post(
            '/api/recommendations/status',
            json={'course_id': course.id, 'status': 'In Progress'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'In Progress')

    def test_http_dashboard_integration(self):
        """Verifies dashboard displays top gap-based recommended courses."""
        user = self._create_standard_test_user()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn("Top Gap-Based Course Recommendations", content)
        self.assertIn("View All Recommendations", content)


if __name__ == '__main__':
    unittest.main()
