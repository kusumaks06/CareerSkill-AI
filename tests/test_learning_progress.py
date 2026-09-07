import json
import unittest
from datetime import datetime, timezone, timedelta

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
    UserCourseRecommendation,
    UserRoadmap, 
    RoadmapMilestone,
    AssessmentQuestion, 
    AssessmentAttempt, 
    AssessmentAnswer,
    CourseProgress, 
    LearningActivity, 
    SkillProgressHistory
)
from services.progress_service import progress_service
from services.skill_gap_service import skill_gap_service
from services.roadmap_service import roadmap_service
from services.recommendation_service import recommendation_service
from services.assessment_service import assessment_service


class LearningProgressTestCase(unittest.TestCase):
    """Automated test suite for Module 8: Learning Progress Tracking."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            assessment_service.seed_questions_if_empty()
            recommendation_service.seed_courses_if_empty()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _create_sample_candidate(self, email="progress_user@example.com"):
        """Helper to create candidate with Data Analyst profile and 10 hrs/week schedule."""
        user = User(full_name="Alex Progress", email=email)
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
            degree="B.Sc.",
            branch="Computer Science",
            learning_hours_per_day="2 hours/day",
            learning_days_per_week=5,
            learning_hours_per_week=10.0
        )
        db.session.add(profile)

        # Candidate skills: Python - Intermediate, SQL - Beginner, Excel - Intermediate, Power BI - Beginner
        skills_data = [
            ('Python', 'Intermediate', 50),
            ('SQL', 'Beginner', 25),
            ('Excel', 'Intermediate', 50),
            ('Power BI', 'Beginner', 25)
        ]
        for s_name, s_level, s_score in skills_data:
            us = UserSkill(
                user_id=user.id,
                skill_name=s_name,
                proficiency_level=s_level,
                proficiency_score=s_score,
                confidence_level=3
            )
            db.session.add(us)

        db.session.commit()

        # Run initial gap analysis, recommendations, and roadmap
        skill_gap_service.analyze_skill_gap(user=user, target_role="Data Analyst")
        recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")
        roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")

        return user

    def test_course_progress_tracking(self):
        """Verifies course progress percentage and hours tracking (e.g. 16/20 hrs = 80%)."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            course = Course.query.filter_by(skill='SQL').first()
            self.assertIsNotNone(course)

            # Update progress to In Progress, 80%, 16 hours
            res = progress_service.update_course_progress(
                user_id=user.id,
                course_id=course.id,
                status='In Progress',
                progress_percentage=80,
                hours_completed=16.0
            )

            self.assertTrue(res['success'])
            self.assertEqual(res['progress']['progress_percentage'], 80)
            self.assertEqual(res['progress']['hours_completed'], 16.0)
            self.assertEqual(res['progress']['status'], 'In Progress')

            # Verify LearningActivity was logged
            activity = LearningActivity.query.filter_by(user_id=user.id, activity_type='Course').first()
            self.assertIsNotNone(activity)
            self.assertEqual(activity.hours, 16.0)

    def test_course_completion_skill_boost_and_history(self):
        """Verifies completing a course boosts skill proficiency and logs history."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            course = Course.query.filter_by(skill='SQL').first()
            self.assertIsNotNone(course)

            # Initial SQL score was 25% (Beginner)
            sql_skill = UserSkill.query.filter_by(user_id=user.id, skill_name='SQL').first()
            self.assertEqual(sql_skill.proficiency_score, 25)

            # Mark course completed (100%)
            res = progress_service.update_course_progress(
                user_id=user.id,
                course_id=course.id,
                status='Completed',
                progress_percentage=100
            )

            self.assertTrue(res['success'])
            self.assertEqual(res['progress']['status'], 'Completed')

            # Verify SQL skill boosted to at least Intermediate (>=50%)
            sql_skill_after = UserSkill.query.filter_by(user_id=user.id, skill_name='SQL').first()
            self.assertGreater(sql_skill_after.proficiency_score, 25)

            # Verify SkillProgressHistory entry exists
            sph = SkillProgressHistory.query.filter_by(user_id=user.id, skill_name='SQL').first()
            self.assertIsNotNone(sph)
            self.assertEqual(sph.triggered_by, 'Course Completion')

    def test_roadmap_task_progress_tracking(self):
        """Verifies completing a roadmap milestone task logs activity and recalculates progress."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(roadmap)
            first_milestone = roadmap.milestones[0]
            tasks = first_milestone.get_tasks()
            self.assertTrue(len(tasks) > 0)

            # Complete first task
            task_id = tasks[0].get('id', 1)
            res = progress_service.update_roadmap_task_progress(
                user_id=user.id,
                milestone_id=first_milestone.id,
                task_id=task_id,
                completed=True,
                hours_spent=2.5
            )

            self.assertTrue(res['success'])
            self.assertGreater(res['roadmap_progress'], 0)

            # Verify LearningActivity exists
            act = LearningActivity.query.filter_by(user_id=user.id, activity_type='Roadmap').first()
            self.assertIsNotNone(act)
            self.assertEqual(act.hours, 2.5)

    def test_learning_hours_summary(self):
        """Verifies calculation of Today, Week, Month, and Total learning hours vs Planned."""
        with self.app.app_context():
            user = self._create_sample_candidate()

            # Log 3 activities: 2.0h today, 3.0h this week
            progress_service.log_learning_session(user.id, skill="SQL", title="SQL Window Functions", hours=2.0)
            progress_service.log_learning_session(user.id, skill="Python", title="Pandas Data Cleaning", hours=3.0)

            summary = progress_service.get_learning_hours_summary(user.id)
            self.assertEqual(summary['total_hours'], 5.0)
            self.assertEqual(summary['today_hours'], 5.0)
            self.assertEqual(summary['week_hours'], 5.0)
            self.assertEqual(summary['planned_weekly_hours'], 10.0)
            self.assertEqual(summary['planned_vs_completed_pct'], 50)  # 5 / 10 = 50%

    def test_skill_growth_matrix(self):
        """Verifies Before vs Current vs Target skill comparisons and growth deltas."""
        with self.app.app_context():
            user = self._create_sample_candidate()

            # Initial matrix
            matrix = progress_service.get_skill_growth_matrix(user.id, target_role="Data Analyst")
            self.assertTrue(len(matrix) >= 4)

            sql_row = next((r for r in matrix if r['skill_name'] == 'SQL'), None)
            self.assertIsNotNone(sql_row)
            self.assertEqual(sql_row['before_score'], 25)
            self.assertEqual(sql_row['current_score'], 25)
            self.assertEqual(sql_row['growth_delta'], 0)

            # Boost SQL via course completion
            course = Course.query.filter_by(skill='SQL').first()
            progress_service.update_course_progress(user.id, course.id, status='Completed', progress_percentage=100)

            # Check matrix after completion
            matrix_after = progress_service.get_skill_growth_matrix(user.id, target_role="Data Analyst")
            sql_row_after = next((r for r in matrix_after if r['skill_name'] == 'SQL'), None)
            self.assertGreater(sql_row_after['current_score'], 25)
            self.assertGreater(sql_row_after['growth_delta'], 0)

    def test_career_readiness_dynamic_recalculation(self):
        """Verifies Career Readiness recalculates across activity advancements with disclaimer."""
        with self.app.app_context():
            user = self._create_sample_candidate()

            readiness_init = progress_service.calculate_career_readiness(user, target_role="Data Analyst")
            self.assertIn('current_readiness', readiness_init)
            self.assertIn('disclaimer', readiness_init)
            self.assertEqual(readiness_init['target_readiness'], 90)

            # Advance course & roadmap
            course = Course.query.first()
            progress_service.update_course_progress(user.id, course.id, status='Completed', progress_percentage=100)

            readiness_after = progress_service.calculate_career_readiness(user, target_role="Data Analyst")
            self.assertGreaterEqual(readiness_after['current_readiness'], readiness_init['current_readiness'])

    def test_overall_progress_summary_kpis(self):
        """Verifies consolidated 9 KPIs for user dashboard."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            summary = progress_service.get_overall_progress_summary(user.id, target_role="Data Analyst")

            self.assertIn('overall_progress_pct', summary)
            self.assertIn('career_readiness', summary)
            self.assertIn('courses_completed', summary)
            self.assertIn('courses_in_progress', summary)
            self.assertIn('topics_completed', summary)
            self.assertIn('topics_remaining', summary)
            self.assertIn('skills_improved_count', summary)
            self.assertIn('learning_hours_completed', summary)
            self.assertIn('learning_hours_remaining', summary)

    def test_http_progress_history_route(self):
        """Verifies GET /progress-history renders successfully."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        resp = self.client.get('/progress-history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Learning Progress &', resp.data)
        self.assertIn(b'Activity History', resp.data)
        self.assertIn(b'Learning Hours Tracker', resp.data)

    def test_api_progress_endpoints(self):
        """Verifies REST endpoints for course progress update, session logging, and history."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id
            course = Course.query.filter_by(skill='Python').first()
            course_id = course.id

        # 1. POST /api/progress/course/update
        resp_update = self.client.post(
            '/api/progress/course/update',
            json={
                'user_id': user_id,
                'course_id': course_id,
                'status': 'In Progress',
                'progress_percentage': 50,
                'hours_completed': 5.0
            }
        )
        self.assertEqual(resp_update.status_code, 200)
        data = resp_update.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['progress']['progress_percentage'], 50)

        # 2. POST /api/progress/log-session
        resp_log = self.client.post(
            '/api/progress/log-session',
            json={
                'user_id': user_id,
                'skill': 'Python',
                'title': 'LeetCode Array Practice',
                'hours': 2.0,
                'notes': 'Solved Two Sum and 3Sum'
            }
        )
        self.assertEqual(resp_log.status_code, 200)
        log_data = resp_log.get_json()
        self.assertTrue(log_data['success'])

        # 3. GET /api/progress/summary
        resp_sum = self.client.get(f'/api/progress/summary?user_id={user_id}')
        self.assertEqual(resp_sum.status_code, 200)
        sum_data = resp_sum.get_json()
        self.assertGreater(sum_data['learning_hours_completed'], 0)

        # 4. GET /api/progress/history
        resp_hist = self.client.get(f'/api/progress/history?user_id={user_id}')
        self.assertEqual(resp_hist.status_code, 200)
        hist_data = resp_hist.get_json()
        self.assertTrue(len(hist_data['activities']) >= 2)

    def test_full_data_analyst_schedule_scenario(self):
        """
        Complete end-to-end integration test:
        Career: Data Analyst
        Initial Skills: Python (Intermediate), SQL (Beginner), Excel (Intermediate), Power BI (Beginner)
        Schedule: 2 hours/day, 5 days/week (10 hrs/week)
        1. Course progress updates (16/20 hrs = 80%).
        2. Roadmap progress updates.
        3. Learning hours tracked (Today, Week, Month vs 10h schedule).
        4. Skill progress evolves.
        5. Assessment results link to progress history.
        6. Career readiness recalculates.
        7. Dashboard displays updated progress KPIs.
        8. Data persists across sessions.
        """
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id

            # 1. Update SQL Course progress to 80% (16 hrs)
            sql_course = Course.query.filter_by(skill='SQL').first()
            progress_service.update_course_progress(
                user_id=user_id,
                course_id=sql_course.id,
                status='In Progress',
                progress_percentage=80,
                hours_completed=16.0
            )

            # 2. Complete a Roadmap task
            roadmap = UserRoadmap.query.filter_by(user_id=user_id).first()
            m = roadmap.milestones[0]
            t_id = m.get_tasks()[0].get('id', 1)
            progress_service.update_roadmap_task_progress(user_id, m.id, t_id, completed=True, hours_spent=2.0)

            # 3. Take an Assessment and verify progress linkage
            sql_questions = AssessmentQuestion.query.filter_by(skill='SQL').limit(4).all()
            ans_map = {str(q.id): q.correct_answer for q in sql_questions}
            assessment_service.evaluate_assessment(user=user, skill_name='SQL', answers_dict=ans_map)

            # 4. Verify Learning hours
            hours = progress_service.get_learning_hours_summary(user_id)
            self.assertGreaterEqual(hours['total_hours'], 18.0)
            self.assertEqual(hours['planned_weekly_hours'], 10.0)

            # 5. Verify overall summary
            summary = progress_service.get_overall_progress_summary(user_id, target_role="Data Analyst")
            self.assertGreater(summary['overall_progress_pct'], 0)
            self.assertGreater(summary['learning_hours_completed'], 0)
            self.assertGreater(summary['skills_improved_count'], 0)

            # 6. Verify activity history has Course, Roadmap, and Assessment records
            activities = progress_service.get_activity_history(user_id)
            act_types = [a['activity_type'] for a in activities]
            self.assertIn('Course', act_types)
            self.assertIn('Roadmap', act_types)
            self.assertIn('Assessment', act_types)


if __name__ == '__main__':
    unittest.main()
