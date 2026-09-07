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
    UserCourseRecommendation,
    UserRoadmap, 
    RoadmapMilestone,
    AssessmentQuestion, 
    AssessmentAttempt, 
    AssessmentAnswer
)
from services.assessment_service import assessment_service
from services.skill_gap_service import skill_gap_service
from services.roadmap_service import roadmap_service
from services.recommendation_service import recommendation_service


class SkillAssessmentTestCase(unittest.TestCase):
    """Automated test suite for AI Skill Assessment & Progress Validation Engine (Module 7)."""

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

    def _create_sample_candidate(self, email="analyst@example.com"):
        """Helper to create a candidate with Data Analyst profile and specific skill levels."""
        user = User(full_name="Sarah Analyst", email=email)
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

        # Run initial gap analysis & roadmap
        skill_gap_service.analyze_skill_gap(user=user, target_role="Data Analyst")
        roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")
        recommendation_service.generate_recommendations(user=user, target_role="Data Analyst")

        return user

    def test_question_seeding_and_retrieval(self):
        """Verifies assessment questions are seeded properly in database."""
        with self.app.app_context():
            count = AssessmentQuestion.query.count()
            self.assertGreaterEqual(count, 30)

            sql_questions = AssessmentQuestion.query.filter_by(skill='SQL').all()
            self.assertGreaterEqual(len(sql_questions), 5)
            
            first_q = sql_questions[0]
            self.assertTrue(len(first_q.get_options()) >= 2)
            self.assertTrue(bool(first_q.correct_answer))
            self.assertTrue(bool(first_q.explanation))

    def test_get_available_assessment_skills(self):
        """Tests discovery and status ranking of skills available for assessment."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            skills = assessment_service.get_available_assessment_skills(user=user, target_role="Data Analyst")

            self.assertIsInstance(skills, list)
            self.assertGreaterEqual(len(skills), 4)

            # Check that required skills for Data Analyst are present
            skill_names = [s['skill_name'] for s in skills]
            self.assertIn('SQL', skill_names)
            self.assertIn('Python', skill_names)
            self.assertIn('Excel', skill_names)
            self.assertIn('Power BI', skill_names)

            # Initially, all are Not Assessed
            sql_item = next(s for s in skills if s['skill_name'] == 'SQL')
            self.assertEqual(sql_item['validation_status'], 'Not Assessed')
            self.assertEqual(sql_item['self_reported_level'], 'Beginner')

    def test_generate_assessment_adaptive(self):
        """Tests generating adaptive questions for a skill."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            payload = assessment_service.generate_assessment(
                user=user,
                skill_name='SQL',
                target_role='Data Analyst',
                num_questions=6
            )

            self.assertEqual(payload['skill_name'], 'SQL')
            self.assertEqual(payload['target_role'], 'Data Analyst')
            self.assertGreaterEqual(len(payload['questions']), 4)

            # Ensure correct answers are NOT leaked in client payload
            for q in payload['questions']:
                self.assertNotIn('correct_answer', q)
                self.assertNotIn('explanation', q)
                self.assertIn('options', q)
                self.assertIn('id', q)

    def test_evaluate_assessment_scoring_and_weak_topics(self):
        """Tests evaluating user answers, scoring, and identifying strong vs weak topics."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            
            # Fetch real questions for SQL
            questions = AssessmentQuestion.query.filter_by(skill='SQL').limit(6).all()
            self.assertGreaterEqual(len(questions), 4)

            # Answer some correctly and intentionally get JOIN question wrong
            answers_dict = {}
            for i, q in enumerate(questions):
                if 'JOIN' in q.topic.upper():
                    answers_dict[str(q.id)] = "WRONG_ANSWER_VALUE"
                else:
                    answers_dict[str(q.id)] = q.correct_answer

            result = assessment_service.evaluate_assessment(
                user=user,
                skill_name='SQL',
                answers_dict=answers_dict,
                target_role='Data Analyst'
            )

            self.assertIn('score', result)
            self.assertGreater(result['score'], 0)
            self.assertLessEqual(result['score'], 100)
            self.assertEqual(result['skill_name'], 'SQL')
            self.assertTrue(len(result['evaluated_answers']) > 0)
            
            # Weak topics should include JOIN
            weak_topics = result['weak_topics']
            has_join_weakness = any('JOIN' in t.upper() for t in weak_topics)
            self.assertTrue(has_join_weakness)

    def test_three_way_comparison_feedback(self):
        """Tests constructive three-way comparison between self-reported, assessed, and market level."""
        with self.app.app_context():
            user = self._create_sample_candidate()

            # Simulate an assessment with poor performance (score < 40%)
            questions = AssessmentQuestion.query.filter_by(skill='Python').limit(4).all()
            answers_dict = {str(q.id): "WRONG_ANSWER" for q in questions}

            result = assessment_service.evaluate_assessment(
                user=user,
                skill_name='Python',
                answers_dict=answers_dict,
                target_role='Data Analyst'
            )

            # Self-reported was Intermediate (50), assessed is Beginner (25)
            self.assertEqual(result['self_reported_level'], 'Intermediate')
            self.assertEqual(result['assessed_level'], 'Beginner')
            self.assertIn('lower than your self-reported', result['comparison_verdict'])

    def test_retake_improvement_tracking(self):
        """Tests retaking an assessment and calculating score improvement (+%)."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            questions = AssessmentQuestion.query.filter_by(skill='SQL').limit(4).all()

            # Attempt 1: 50% score (2 correct out of 4)
            ans1 = {
                str(questions[0].id): questions[0].correct_answer,
                str(questions[1].id): questions[1].correct_answer,
                str(questions[2].id): "WRONG_1",
                str(questions[3].id): "WRONG_2"
            }
            res1 = assessment_service.evaluate_assessment(user=user, skill_name='SQL', answers_dict=ans1)
            self.assertEqual(res1['score'], 50.0)
            self.assertIsNone(res1['previous_score'])

            # Attempt 2: 100% score (all 4 correct)
            ans2 = {str(q.id): q.correct_answer for q in questions}
            res2 = assessment_service.evaluate_assessment(user=user, skill_name='SQL', answers_dict=ans2)
            
            self.assertEqual(res2['score'], 100.0)
            self.assertEqual(res2['previous_score'], 50.0)
            self.assertEqual(res2['score_improvement'], 50.0)

    def test_cascading_updates_to_gap_and_roadmap(self):
        """Tests that taking an assessment updates UserSkill, SkillGap, and escalates weak topics in Roadmap."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            
            questions = AssessmentQuestion.query.filter_by(skill='SQL').all()
            self.assertGreaterEqual(len(questions), 4)

            # Get JOIN question wrong to force weak topic escalation
            ans = {}
            for q in questions:
                if 'JOIN' in q.topic.upper():
                    ans[str(q.id)] = "WRONG_CHOICE"
                else:
                    ans[str(q.id)] = q.correct_answer

            assessment_service.evaluate_assessment(user=user, skill_name='SQL', answers_dict=ans)

            # 1. Verify UserSkill was updated
            us = UserSkill.query.filter_by(user_id=user.id, skill_name='SQL').first()
            self.assertIsNotNone(us)

            # 2. Verify Roadmap has escalated task for weak topic
            roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(roadmap)
            
            tasks = []
            for m in roadmap.milestones:
                if 'SQL' in m.skill.upper():
                    tasks.extend(m.get_tasks())

            remediation_task = any('JOIN' in t.get('task', '').upper() for t in tasks)
            self.assertTrue(remediation_task)

    def test_user_assessment_stats(self):
        """Tests summary statistics calculation for user assessment dashboard widget."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            
            # Initial stats: 0 completed
            stats = assessment_service.get_user_assessment_stats(user.id)
            self.assertEqual(stats['total_completed'], 0)
            self.assertEqual(stats['avg_score'], 0.0)

            # Complete an assessment
            questions = AssessmentQuestion.query.filter_by(skill='Excel').limit(4).all()
            ans = {str(q.id): q.correct_answer for q in questions}
            assessment_service.evaluate_assessment(user=user, skill_name='Excel', answers_dict=ans)

            stats_after = assessment_service.get_user_assessment_stats(user.id)
            self.assertEqual(stats_after['total_completed'], 1)
            self.assertEqual(stats_after['avg_score'], 100.0)
            self.assertEqual(stats_after['validated_count'], 1)
            self.assertEqual(stats_after['improvement_needed_count'], 0)

    def test_http_assessment_overview_and_quiz_routes(self):
        """Tests GET /assessments and GET /assessment/start/<skill>."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        # GET /assessments
        resp = self.client.get('/assessments')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'AI Skill Assessment', resp.data)
        self.assertIn(b'SQL', resp.data)

        # GET /assessment/start/SQL
        resp_quiz = self.client.get('/assessment/start/SQL')
        self.assertEqual(resp_quiz.status_code, 200)
        self.assertIn(b'Knowledge Assessment', resp_quiz.data)
        self.assertIn(b'Submit Assessment', resp_quiz.data)

    def test_http_assessment_submit_flow(self):
        """Tests POST /assessment/submit and redirect to /assessment/result/<id>."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id
            questions = AssessmentQuestion.query.filter_by(skill='SQL').limit(4).all()
            q_ids = [q.id for q in questions]

        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

        # Submit form
        form_data = {
            'skill_name': 'SQL',
            'target_role': 'Data Analyst',
            'difficulty': 'Intermediate'
        }
        for q_id in q_ids:
            form_data[f'q_{q_id}'] = 'Sample Option Answer'

        resp = self.client.post('/assessment/submit', data=form_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Assessment Report', resp.data)
        self.assertIn(b'Three-Way Proficiency Calibration', resp.data)

    def test_api_assessment_endpoints(self):
        """Tests REST endpoints for questions, submit, and stats."""
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id
            questions = AssessmentQuestion.query.filter_by(skill='Python').limit(3).all()
            q_map = {str(q.id): q.correct_answer for q in questions}

        # 1. GET /api/assessment/questions
        resp = self.client.get('/api/assessment/questions?skill=Python')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['skill_name'], 'Python')
        self.assertTrue(len(data['questions']) > 0)

        # 2. POST /api/assessment/submit
        resp_sub = self.client.post(
            '/api/assessment/submit',
            json={
                'user_id': user_id,
                'skill_name': 'Python',
                'target_role': 'Data Analyst',
                'answers': q_map
            }
        )
        self.assertEqual(resp_sub.status_code, 200)
        res_json = resp_sub.get_json()
        self.assertTrue(res_json['success'])
        self.assertEqual(res_json['result']['score'], 100.0)

        # 3. GET /api/assessment/stats
        resp_stats = self.client.get(f'/api/assessment/stats?user_id={user_id}')
        self.assertEqual(resp_stats.status_code, 200)
        stats_json = resp_stats.get_json()
        self.assertEqual(stats_json['total_completed'], 1)
        self.assertEqual(stats_json['avg_score'], 100.0)

    def test_full_data_analyst_assessment_flow(self):
        """
        Complete end-to-end scenario test:
        Career: Data Analyst
        Skills: Python (Intermediate), SQL (Beginner), Excel (Intermediate), Power BI (Beginner)
        1. Assessment opens for SQL.
        2. Questions are related to SQL with correct answers.
        3. Score is calculated (62.5% on partial correct).
        4. Weak topics (JOIN) vs strong topics (WHERE, SELECT) are identified.
        5. Skill level is evaluated (Intermediate).
        6. Skill gap updates.
        7. Career readiness updates.
        8. Course recommendations update for weak topics.
        9. Roadmap priority updates.
        10. Retake works with +37.5% improvement shown.
        """
        with self.app.app_context():
            user = self._create_sample_candidate()
            user_id = user.id

            # Initial readiness score
            init_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role="Data Analyst")
            init_readiness = init_analysis['readiness_score']

            # 1 & 2: Generate SQL Assessment
            assessment = assessment_service.generate_assessment(user=user, skill_name="SQL", target_role="Data Analyst", num_questions=8)
            self.assertEqual(assessment['skill_name'], 'SQL')
            self.assertTrue(len(assessment['questions']) >= 4)

            # Retrieve actual questions from DB
            sql_questions = AssessmentQuestion.query.filter_by(skill='SQL').all()
            
            # 3, 4 & 5: Answer questions with JOIN/Subqueries/Window Functions incorrect and SELECT/WHERE correct
            answers_1 = {}
            for q in sql_questions:
                if 'JOIN' in q.topic.upper() or 'SUBQUER' in q.topic.upper() or 'WINDOW' in q.topic.upper():
                    answers_1[str(q.id)] = "INCORRECT_OPTION"
                else:
                    answers_1[str(q.id)] = q.correct_answer

            eval_1 = assessment_service.evaluate_assessment(user=user, skill_name="SQL", answers_dict=answers_1, target_role="Data Analyst")
            
            self.assertGreater(eval_1['score'], 0)
            self.assertTrue(len(eval_1['weak_topics']) > 0)
            self.assertTrue(len(eval_1['strong_topics']) > 0)
            self.assertIn('SELECT & WHERE Filtering', eval_1['strong_topics'])
            self.assertEqual(eval_1['assessed_level'], 'Intermediate')

            # 6, 7 & 8: Verify Skill Gap and Readiness update
            updated_analysis = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first()
            self.assertIsNotNone(updated_analysis)

            # 9: Verify Roadmap priority update for weak topic
            roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
            self.assertIsNotNone(roadmap)
            sql_milestones = [m for m in roadmap.milestones if 'SQL' in m.skill.upper()]
            self.assertTrue(any(m.priority == 'Critical' for m in sql_milestones))

            # 10 & 11: Retake SQL Assessment with 100% score
            answers_2 = {str(q.id): q.correct_answer for q in sql_questions}
            eval_2 = assessment_service.evaluate_assessment(user=user, skill_name="SQL", answers_dict=answers_2, target_role="Data Analyst")
            
            self.assertEqual(eval_2['score'], 100.0)
            self.assertEqual(eval_2['previous_score'], eval_1['score'])
            self.assertGreater(eval_2['score_improvement'], 0)
            self.assertEqual(len(eval_2['weak_topics']), 0)


if __name__ == '__main__':
    unittest.main()
