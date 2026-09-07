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
    Course,
    CourseProgress,
    CourseFeedback,
    UserCourseRecommendation,
    UserRoadmap,
    RoadmapMilestone,
    LearningActivity
)
from services.feedback_service import feedback_service
from services.progress_service import progress_service
from services.recommendation_service import recommendation_service
from services.roadmap_service import roadmap_service
from services.assessment_service import assessment_service


class CourseFeedbackTestCase(unittest.TestCase):
    """Automated test suite for Module 9: Course Completion & User Feedback."""

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

    def _create_test_user(self, email="test_student@example.com", name="Jane Candidate"):
        """Helper to create an authenticated candidate with target career and roadmap."""
        user = User(full_name=name, email=email)
        user.set_password("StudentPass123!")
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

        # Add initial skill
        sql_skill = UserSkill(
            user_id=user.id,
            skill_name="SQL",
            proficiency_level="Beginner",
            proficiency_score=25,
            confidence_level=3
        )
        db.session.add(sql_skill)
        db.session.commit()

        # Generate roadmap
        roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")

        return user

    def test_feedback_model_creation_and_relationships(self):
        """Test CourseFeedback model fields, relations, and to_dict method."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()
            self.assertIsNotNone(course)

            feedback = CourseFeedback(
                user_id=user.id,
                course_id=course.id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes",
                liked_aspects="Interactive query runner",
                improvement_suggestions="More advanced joins",
                would_recommend="Yes"
            )
            db.session.add(feedback)
            db.session.commit()

            # Check DB record
            saved = db.session.get(CourseFeedback, feedback.id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.rating, 5)
            self.assertEqual(saved.usefulness, "Very Useful")
            self.assertEqual(saved.improved_skill, "Yes")
            self.assertEqual(saved.would_recommend, "Yes")

            # Check relationships and alias properties
            self.assertEqual(len(user.feedbacks), 1)
            self.assertEqual(user.feedbacks[0].id, saved.id)
            self.assertIn(saved, course.feedbacks)
            self.assertEqual(saved.skill_improvement, "Yes")
            self.assertEqual(saved.comments, "Interactive query runner")
            self.assertEqual(saved.recommendation, "Yes")

            # Check to_dict()
            d = saved.to_dict()
            self.assertEqual(d['rating'], 5)
            self.assertEqual(d['user_name'], "Jane Candidate")
            self.assertEqual(d['course_title'], course.title)
            self.assertEqual(d['liked_aspects'], "Interactive query runner")
            self.assertEqual(d['comments'], "Interactive query runner")
            self.assertEqual(d['skill_improvement'], "Yes")
            self.assertEqual(d['recommendation'], "Yes")
            self.assertIn("CourseFeedback", repr(saved))

    def test_submit_feedback_service_new_and_course_completion(self):
        """Test feedback_service submits feedback and automatically marks course completed."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()

            result = feedback_service.submit_or_update_feedback(
                user_id=user.id,
                course_id=course.id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes",
                liked_aspects="Crystal clear explanations",
                improvement_suggestions="None",
                would_recommend="Yes"
            )

            self.assertTrue(result['success'])
            self.assertFalse(result['is_update'])
            self.assertEqual(result['feedback']['rating'], 5)

            # Verify CourseProgress is 100% and Completed
            cp = CourseProgress.query.filter_by(user_id=user.id, course_id=course.id).first()
            self.assertIsNotNone(cp)
            self.assertEqual(cp.status, 'Completed')
            self.assertEqual(cp.progress_percentage, 100)

            # Verify UserSkill was boosted
            us = UserSkill.query.filter_by(user_id=user.id, skill_name="SQL").first()
            self.assertGreater(us.proficiency_score, 25)

            # Verify Learning Activity logged
            activities = LearningActivity.query.filter_by(user_id=user.id).all()
            self.assertTrue(any(a.activity_type == 'Course' for a in activities))

    def test_prevent_duplicate_feedback_and_update_in_place(self):
        """Test submitting feedback for same course updates existing record rather than creating duplicates."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()

            # First submission
            res1 = feedback_service.submit_or_update_feedback(
                user_id=user.id,
                course_id=course.id,
                rating=4,
                usefulness="Useful",
                improved_skill="Partially",
                liked_aspects="Good content",
                improvement_suggestions="Add more quizzes",
                would_recommend="Yes"
            )
            self.assertTrue(res1['success'])
            self.assertFalse(res1['is_update'])

            # Verify 1 record in DB
            count1 = CourseFeedback.query.filter_by(user_id=user.id, course_id=course.id).count()
            self.assertEqual(count1, 1)

            # Second submission (edit / update)
            res2 = feedback_service.submit_or_update_feedback(
                user_id=user.id,
                course_id=course.id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes",
                liked_aspects="Updated: Even better on second review",
                improvement_suggestions="None at all",
                would_recommend="Yes"
            )
            self.assertTrue(res2['success'])
            self.assertTrue(res2['is_update'])
            self.assertIn("updated", res2['message'].lower())

            # Verify still only 1 record exists in DB with updated values
            feedbacks = CourseFeedback.query.filter_by(user_id=user.id, course_id=course.id).all()
            self.assertEqual(len(feedbacks), 1)
            self.assertEqual(feedbacks[0].rating, 5)
            self.assertEqual(feedbacks[0].usefulness, "Very Useful")
            self.assertEqual(feedbacks[0].liked_aspects, "Updated: Even better on second review")

    def test_get_user_feedbacks(self):
        """Test retrieval of user's submitted feedbacks for dashboard display."""
        with self.app.app_context():
            user = self._create_test_user()
            courses = Course.query.limit(2).all()

            for i, c in enumerate(courses):
                feedback_service.submit_or_update_feedback(
                    user_id=user.id,
                    course_id=c.id,
                    rating=4 + i,
                    usefulness="Very Useful",
                    improved_skill="Yes"
                )

            user_feedbacks = feedback_service.get_user_feedbacks(user.id)
            self.assertEqual(len(user_feedbacks), 2)
            self.assertEqual(user_feedbacks[0]['user_id'], user.id)

    def test_admin_feedback_listing_and_analytics(self):
        """Test admin feedback filtering and analytics aggregation."""
        with self.app.app_context():
            u1 = self._create_test_user(email="user1@example.com", name="User One")
            u2 = self._create_test_user(email="user2@example.com", name="User Two")
            courses = Course.query.limit(2).all()

            # Submit 2 feedbacks
            feedback_service.submit_or_update_feedback(
                user_id=u1.id,
                course_id=courses[0].id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes",
                liked_aspects="Exceptional pacing",
                would_recommend="Yes"
            )
            feedback_service.submit_or_update_feedback(
                user_id=u2.id,
                course_id=courses[1].id,
                rating=3,
                usefulness="Partially Useful",
                improved_skill="Partially",
                liked_aspects="Decent",
                would_recommend="No"
            )

            # Test analytics
            analytics = feedback_service.get_feedback_analytics()
            self.assertEqual(analytics['total_reviews'], 2)
            self.assertEqual(analytics['average_rating'], 4.0)
            self.assertEqual(analytics['rating_counts'][5], 1)
            self.assertEqual(analytics['rating_counts'][3], 1)
            self.assertEqual(analytics['usefulness_counts']['Very Useful'], 1)
            self.assertEqual(analytics['recommend_counts']['Yes'], 1)
            self.assertEqual(analytics['recommend_counts']['No'], 1)

            # Test admin search
            search_u1 = feedback_service.get_all_feedbacks_for_admin(search_query="User One")
            self.assertEqual(len(search_u1), 1)
            self.assertEqual(search_u1[0]['user_name'], "User One")

            # Test admin course filter
            course_filtered = feedback_service.get_all_feedbacks_for_admin(course_id=courses[0].id)
            self.assertEqual(len(course_filtered), 1)
            self.assertEqual(course_filtered[0]['course_id'], courses[0].id)

            # Test admin rating filter
            high_rated = feedback_service.get_all_feedbacks_for_admin(min_rating=5)
            self.assertEqual(len(high_rated), 1)
            self.assertEqual(high_rated[0]['rating'], 5)

            # Test admin usefulness filter
            partial_useful = feedback_service.get_all_feedbacks_for_admin(usefulness="Partially Useful")
            self.assertEqual(len(partial_useful), 1)

    def test_complete_course_action_route(self):
        """Test GET/POST /course/<id>/complete marks course 100% and redirects to feedback."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()
            user_id = user.id
            course_id = course.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        # Trigger complete course action
        resp = self.client.post(f'/course/{course_id}/complete', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/course/{course_id}/feedback', resp.headers['Location'])

        # Verify course progress is 100%
        with self.app.app_context():
            cp = CourseProgress.query.filter_by(user_id=user_id, course_id=course_id).first()
            self.assertIsNotNone(cp)
            self.assertEqual(cp.status, 'Completed')
            self.assertEqual(cp.progress_percentage, 100)

            # Verify roadmap milestone synchronized
            roadmap = UserRoadmap.query.filter_by(user_id=user_id).first()
            self.assertGreater(roadmap.completion_percentage, 0)

    def test_course_feedback_web_form_and_dashboard_display(self):
        """Test full web form GET, POST, and verifying review renders in dashboard."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()
            user_id = user.id
            course_id = course.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        # 1. GET feedback page
        get_resp = self.client.get(f'/course/{course_id}/feedback')
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn(b"Course Feedback", get_resp.data)
        import html
        self.assertIn(html.escape(course.title).encode('utf-8'), get_resp.data)

        # 2. POST feedback
        post_resp = self.client.post(f'/course/{course_id}/feedback', data={
            'rating': '5',
            'usefulness': 'Very Useful',
            'improved_skill': 'Yes',
            'liked_aspects': 'Great hands-on coding challenges',
            'improvement_suggestions': 'More challenging scenarios',
            'would_recommend': 'Yes'
        }, follow_redirects=True)

        self.assertEqual(post_resp.status_code, 200)
        self.assertIn(b"submitted successfully", post_resp.data)

        # 3. GET Dashboard and verify feedback section shows review
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b"My Course Feedback & Ratings", dash_resp.data)
        self.assertIn(b"Great hands-on coding challenges", dash_resp.data)
        self.assertIn(b"Edit Review", dash_resp.data)

    def test_ajax_feedback_endpoints(self):
        """Test POST /api/course/feedback and GET /api/course/<id>/feedback."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()
            user_id = user.id
            course_id = course.id

        # AJAX POST submission
        post_resp = self.client.post('/api/course/feedback', json={
            'user_id': user_id,
            'course_id': course_id,
            'rating': 5,
            'usefulness': 'Very Useful',
            'improved_skill': 'Yes',
            'liked_aspects': 'API submission test',
            'improvement_suggestions': 'None',
            'would_recommend': 'Yes'
        })
        self.assertEqual(post_resp.status_code, 200)
        data = json.loads(post_resp.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['feedback']['rating'], 5)

        # AJAX GET retrieval
        get_resp = self.client.get(f'/api/course/{course_id}/feedback?user_id={user_id}')
        self.assertEqual(get_resp.status_code, 200)
        get_data = json.loads(get_resp.data)
        self.assertTrue(get_data['success'])
        self.assertEqual(get_data['feedback']['liked_aspects'], 'API submission test')

    def test_admin_feedback_page_and_api(self):
        """Test GET /admin/feedback and GET /api/admin/feedbacks."""
        with self.app.app_context():
            user = self._create_test_user()
            course = Course.query.filter_by(skill="SQL").first()
            feedback_service.submit_or_update_feedback(
                user_id=user.id,
                course_id=course.id,
                rating=5,
                usefulness="Very Useful",
                improved_skill="Yes",
                liked_aspects="Top notch content"
            )

        # GET Admin HTML view
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['is_admin'] = True
        resp = self.client.get('/admin/feedback')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Course Feedback", resp.data)
        self.assertIn(b"Top notch content", resp.data)
        self.assertIn(b"Jane Candidate", resp.data)

        # GET Admin HTML with course filter
        resp_filtered = self.client.get(f'/admin/feedback?course_id={course.id}')
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertIn(b"Top notch content", resp_filtered.data)

        # GET Admin JSON API
        api_resp = self.client.get(f'/api/admin/feedbacks?course_id={course.id}')
        self.assertEqual(api_resp.status_code, 200)
        api_data = json.loads(api_resp.data)
        self.assertTrue(api_data['success'])
        self.assertGreaterEqual(api_data['analytics']['total_reviews'], 1)
        self.assertEqual(len(api_data['feedbacks']), 1)

    def test_full_user_journey_flow(self):
        """
        Complete end-to-end flow test:
        Login -> Course Recommendations -> Start Course -> Update Progress -> Complete Course -> Submit Feedback -> Dashboard Updated -> Admin Can View Feedback.
        """
        with self.app.app_context():
            user = self._create_test_user(email="journey_user@example.com", name="Taylor Explorer")
            course = Course.query.filter_by(skill="SQL").first()
            user_id = user.id
            course_id = course.id

        # 1. Login
        login_resp = self.client.post('/login', data={
            'email': 'journey_user@example.com',
            'password': 'StudentPass123!'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # 2. View Course Recommendations
        recs_resp = self.client.get('/course-recommendations')
        self.assertEqual(recs_resp.status_code, 200)
        import html
        self.assertIn(html.escape(course.title).encode('utf-8'), recs_resp.data)

        # 3. Start Course (In Progress)
        start_resp = self.client.post('/api/recommendations/status', json={
            'user_id': user_id,
            'course_id': course_id,
            'status': 'In Progress'
        })
        self.assertEqual(start_resp.status_code, 200)

        # 4. Update Course Progress (50%)
        prog_resp = self.client.post('/api/progress/course/update', json={
            'user_id': user_id,
            'course_id': course_id,
            'status': 'In Progress',
            'progress_percentage': 50,
            'hours_completed': 5.0
        })
        self.assertEqual(prog_resp.status_code, 200)

        # 5. Complete Course via action route -> redirects to feedback
        complete_resp = self.client.post(f'/course/{course_id}/complete', follow_redirects=True)
        self.assertEqual(complete_resp.status_code, 200)
        self.assertIn(b"Course Feedback", complete_resp.data)

        # 6. Submit Feedback
        feedback_resp = self.client.post(f'/course/{course_id}/feedback', data={
            'rating': '5',
            'usefulness': 'Very Useful',
            'improved_skill': 'Yes',
            'liked_aspects': 'Great practical queries and CTE examples',
            'improvement_suggestions': 'Add database indexing deep dive',
            'would_recommend': 'Yes'
        }, follow_redirects=True)
        self.assertEqual(feedback_resp.status_code, 200)

        # 7. Verify Dashboard is updated with review & 100% course completion
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b"My Course Feedback & Ratings", dash_resp.data)
        self.assertIn(b"Great practical queries and CTE examples", dash_resp.data)

        # 8. Verify Admin can view Taylor's feedback
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = True
        admin_resp = self.client.get('/admin/feedback')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn(b"Taylor Explorer", admin_resp.data)
        self.assertIn(b"Great practical queries and CTE examples", admin_resp.data)


if __name__ == '__main__':
    unittest.main()
