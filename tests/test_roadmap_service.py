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
    Course,
    UserRoadmap,
    RoadmapMilestone
)
from services.roadmap_service import roadmap_service
from services.recommendation_service import recommendation_service

class RoadmapServiceTestCase(unittest.TestCase):
    """Test suite for AI Career Roadmap Generator (Module 5)."""

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Seed courses for resource attachments
        recommendation_service.seed_courses_if_empty()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_standard_candidate(self, weekly_hours=10.0):
        """Helper to create candidate with standard profile and skills."""
        user = User(
            full_name="Morgan Roadmap Candidate",
            email="morgan.roadmap@example.com"
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
            learning_hours_per_week=weekly_hours,
            preferred_difficulty="Balanced"
        )
        profile.set_learning_preferences(["Video Courses", "Hands-on Practice", "Projects"])
        profile.set_career_goals(["Become a professional Data Analyst"])
        db.session.add(profile)

        tc = TargetCareer(
            user_id=user.id,
            career_name="Data Analyst",
            normalized_career_name="data analyst"
        )
        db.session.add(tc)

        # Log initial skills: Python (Intermediate), SQL (Beginner), Excel (Intermediate)
        skills = [
            ("Python", "Intermediate", 50),
            ("SQL", "Beginner", 25),
            ("Excel", "Intermediate", 50)
        ]
        for name, level, score in skills:
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

    def test_roadmap_models_and_progress_calculation(self):
        """Verifies UserRoadmap and RoadmapMilestone models, JSON fields, and progress arithmetic."""
        user = self._create_standard_candidate()
        
        roadmap = UserRoadmap(
            user_id=user.id,
            target_role="Data Analyst",
            total_weeks=12,
            total_hours=120.0,
            weekly_hours=10.0,
            completion_percentage=0,
            status='In Progress'
        )
        db.session.add(roadmap)
        db.session.commit()

        m1 = RoadmapMilestone(
            roadmap_id=roadmap.id,
            phase_number=1,
            phase_name="Foundations & Prerequisites",
            week_start=1,
            week_end=2,
            title="SQL Foundations",
            skill="SQL",
            priority="Critical",
            estimated_hours=20.0
        )
        m1.set_tasks([
            {'id': 1, 'text': 'SELECT & WHERE', 'completed': False},
            {'id': 2, 'text': 'GROUP BY & HAVING', 'completed': False}
        ])
        m1.set_resources([{'title': 'SQL for Data Science', 'provider': 'Coursera'}])
        db.session.add(m1)
        db.session.commit()

        self.assertEqual(roadmap.calculate_progress(), 0)

        # Complete 1 of 2 tasks
        tasks = m1.get_tasks()
        tasks[0]['completed'] = True
        m1.set_tasks(tasks)
        db.session.commit()

        self.assertEqual(roadmap.calculate_progress(), 50)
        self.assertEqual(roadmap.status, 'In Progress')

        # Complete second task
        tasks[1]['completed'] = True
        m1.set_tasks(tasks)
        m1.is_completed = True
        db.session.commit()

        self.assertEqual(roadmap.calculate_progress(), 100)
        self.assertEqual(roadmap.status, 'Completed')

    def test_roadmap_generation_5_phases_and_sequencing(self):
        """
        Verifies roadmap generator produces an ordered 5-phase pathway:
        Phase 1: Foundations
        Phase 2: Core Tool Mastery
        Phase 3: Advanced Specialization
        Phase 4: Capstone Portfolio Projects
        Phase 5: Technical Interview Prep
        """
        user = self._create_standard_candidate()
        data = roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")

        self.assertEqual(data['target_role'], "Data Analyst")
        self.assertGreaterEqual(data['total_weeks'], 4)
        self.assertGreater(data['total_hours'], 40)
        self.assertIn('phases', data)
        self.assertEqual(len(data['phases']), 5)

        # Verify phase numbers
        phase_numbers = [p['number'] for p in data['phases']]
        self.assertEqual(phase_numbers, [1, 2, 3, 4, 5])

        # Verify milestone skills and tasks
        milestones = data['milestones']
        self.assertGreater(len(milestones), 4)

        # Check milestone properties
        for m in milestones:
            self.assertIn('phase_number', m)
            self.assertIn('week_start', m)
            self.assertIn('week_end', m)
            self.assertGreaterEqual(m['week_end'], m['week_start'])
            self.assertIn('tasks', m)
            self.assertGreater(len(m['tasks']), 0)
            self.assertIn('checkpoint_title', m)

        # Verify persistence in SQLite
        saved_roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(saved_roadmap)
        self.assertEqual(len(saved_roadmap.milestones), len(milestones))

    def test_velocity_aware_milestone_weeks(self):
        """Verifies that milestone durations and total weeks scale with weekly study velocity."""
        user_fast = self._create_standard_candidate(weekly_hours=20.0)
        fast_data = roadmap_service.generate_roadmap(user=user_fast, target_role="Data Analyst")

        user_slow = User(full_name="Slow Candidate", email="slow@example.com")
        user_slow.set_password("Pass1234")
        db.session.add(user_slow)
        db.session.commit()

        p_slow = UserProfile(
            user_id=user_slow.id,
            learning_hours_per_week=5.0
        )
        db.session.add(p_slow)
        db.session.commit()

        slow_data = roadmap_service.generate_roadmap(user=user_slow, target_role="Data Analyst")

        # Fast velocity (20h/wk) should take fewer total weeks than slow velocity (5h/wk)
        self.assertLess(fast_data['total_weeks'], slow_data['total_weeks'])

    def test_custom_career_role_roadmap(self):
        """Verifies custom synthesized roles (e.g. Healthcare Data Analyst) generate valid roadmaps."""
        user = self._create_standard_candidate()
        data = roadmap_service.generate_roadmap(user=user, target_role="Healthcare Data Analyst")

        self.assertEqual(data['target_role'], "Healthcare Data Analyst")
        self.assertGreater(len(data['milestones']), 0)
        self.assertEqual(len(data['phases']), 5)

    def test_interactive_task_toggle_ajax(self):
        """Verifies POST /api/roadmap/task-toggle updates task completion and overall progress."""
        user = self._create_standard_candidate()
        data = roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")
        roadmap_id = data['id']
        first_milestone = data['milestones'][0]
        first_task = first_milestone['tasks'][0]

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.post(
            '/api/roadmap/task-toggle',
            json={
                'roadmap_id': roadmap_id,
                'milestone_id': first_milestone['id'],
                'task_id': first_task['id'],
                'completed': True
            }
        )
        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertTrue(res_json['success'])
        self.assertTrue(res_json['task_completed'])
        self.assertGreater(res_json['overall_progress'], 0)

    def test_milestone_status_completion(self):
        """Verifies POST /api/roadmap/milestone-status updates entire milestone status."""
        user = self._create_standard_candidate()
        data = roadmap_service.generate_roadmap(user=user, target_role="Data Analyst")
        roadmap_id = data['id']
        first_milestone = data['milestones'][0]

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.post(
            '/api/roadmap/milestone-status',
            json={
                'roadmap_id': roadmap_id,
                'milestone_id': first_milestone['id'],
                'is_completed': True
            }
        )
        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertTrue(res_json['success'])
        self.assertTrue(res_json['is_completed'])

    def test_http_roadmap_view_route(self):
        """Verifies GET /roadmap renders HTTP 200 with complete interactive UI."""
        user = self._create_standard_candidate()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/roadmap')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn("AI Career Learning Roadmap", html)
        self.assertIn("Data Analyst", html)
        self.assertIn("PHASE 1", html)
        self.assertIn("Actionable Learning Tasks", html)
        self.assertIn("Checkpoint", html)

    def test_http_roadmap_generate_route(self):
        """Verifies POST /roadmap/generate regenerates pathway and redirects."""
        user = self._create_standard_candidate()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.post('/roadmap/generate', data={'target_role': 'Data Analyst'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/roadmap'))

    def test_http_api_roadmap_data_route(self):
        """Verifies GET /api/roadmap-data returns structured roadmap JSON."""
        user = self._create_standard_candidate()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/api/roadmap-data')
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertEqual(json_data['target_role'], 'Data Analyst')
        self.assertIn('milestones', json_data)
        self.assertIn('phases', json_data)

    def test_dashboard_roadmap_widget(self):
        """Verifies dashboard includes the active AI Learning Roadmap widget."""
        user = self._create_standard_candidate()

        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn("Active AI Milestone Roadmap", html)
        self.assertIn("Open Interactive Roadmap", html)
        self.assertIn("My Roadmap", html)


if __name__ == '__main__':
    unittest.main()
