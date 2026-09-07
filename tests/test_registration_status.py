import unittest
from app import create_app
from models import db, User, UserProfile, UserSkill, TargetCareer


class TestRegistrationStatus(unittest.TestCase):
    """Test suite for Current Status selection and dynamic data capture during registration."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_student_registration(self):
        """Test registration as Student captures education, degree, branch, and semester."""
        res = self.client.post('/get-started', data={
            'full_name': 'Maya Student',
            'email': 'maya.student@example.com',
            'password': 'Password123!',
            'target_role': 'Data Analyst',
            'current_status': 'Student',
            'student_education': "Undergraduate / Bachelor's",
            'student_degree': 'BE / BTech',
            'student_branch': 'Artificial Intelligence & Data Science',
            'student_semester_year': '3rd Year (Sem 5-6)'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Verify first-time welcome message
        self.assertIn("Welcome to CareerSkill AI,", html)
        self.assertIn("Maya Student", html)
        self.assertNotIn("Welcome back,", html)

        # Verify DB records
        with self.app.app_context():
            user = User.query.filter_by(email='maya.student@example.com').first()
            self.assertIsNotNone(user)
            profile = user.user_profile
            self.assertIsNotNone(profile)
            self.assertEqual(profile.current_status, 'Student')
            self.assertEqual(profile.degree, 'BE / BTech')
            self.assertEqual(profile.branch, 'Artificial Intelligence & Data Science')
            self.assertEqual(profile.current_semester_year, '3rd Year (Sem 5-6)')

    def test_fresher_registration_with_skills(self):
        """Test registration as Fresher / Job Seeker captures qualification, grad year, and existing skills."""
        res = self.client.post('/register', data={
            'full_name': 'Rohan Fresher',
            'email': 'rohan.fresher@example.com',
            'password': 'Password123!',
            'target_role': 'Python Developer',
            'current_status': 'Fresher / Job Seeker',
            'fresher_qualification': "Bachelor's (BE/BTech/BCA/BSc)",
            'fresher_grad_year': '2025',
            'fresher_skills': 'Python, SQL, Git'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Welcome to CareerSkill AI,", html)
        self.assertIn("Rohan Fresher", html)

        with self.app.app_context():
            user = User.query.filter_by(email='rohan.fresher@example.com').first()
            self.assertIsNotNone(user)
            profile = user.user_profile
            self.assertIsNotNone(profile)
            self.assertEqual(profile.current_status, 'Fresher / Job Seeker')
            self.assertEqual(profile.graduation_year, '2025')
            self.assertIn('Python', profile.existing_skills)

            # Verify UserSkill records populated
            skills = {s.skill_name: s.proficiency_level for s in user.skills}
            self.assertIn('Python', skills)
            self.assertIn('SQL', skills)
            self.assertIn('Git', skills)

    def test_working_professional_registration(self):
        """Test registration as Working Professional captures role, experience, and skills."""
        res = self.client.post('/register', data={
            'full_name': 'David Pro',
            'email': 'david.pro@example.com',
            'password': 'Password123!',
            'target_role': 'Machine Learning Engineer',
            'current_status': 'Working Professional',
            'prof_current_role': 'Junior Software Engineer',
            'prof_experience_years': '3-5 years',
            'prof_skills': 'Python, Docker, AWS, PostgreSQL'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Welcome to CareerSkill AI,", html)
        self.assertIn("David Pro", html)

        with self.app.app_context():
            user = User.query.filter_by(email='david.pro@example.com').first()
            self.assertIsNotNone(user)
            profile = user.user_profile
            self.assertIsNotNone(profile)
            self.assertEqual(profile.current_status, 'Working Professional')
            self.assertEqual(profile.current_job_role, 'Junior Software Engineer')
            self.assertEqual(profile.years_of_experience, '3-5 years')

            # Verify intermediate proficiency assigned for professional
            skills = {s.skill_name: s.proficiency_level for s in user.skills}
            self.assertIn('Docker', skills)
            self.assertEqual(skills['Docker'], 'Intermediate')

    def test_career_switcher_registration(self):
        """Test registration as Career Switcher captures previous role and transferable skills."""
        res = self.client.post('/get-started', data={
            'full_name': 'Elena Switcher',
            'email': 'elena.switcher@example.com',
            'password': 'Password123!',
            'target_role': 'Data Analyst',
            'current_status': 'Career Switcher',
            'switcher_previous_role': 'Financial Analyst',
            'switcher_experience_years': '3-5 years',
            'switcher_skills': 'Excel, Statistics, SQL, Tableau'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Welcome to CareerSkill AI,", html)

        with self.app.app_context():
            user = User.query.filter_by(email='elena.switcher@example.com').first()
            self.assertIsNotNone(user)
            profile = user.user_profile
            self.assertEqual(profile.current_status, 'Career Switcher')
            self.assertEqual(profile.previous_role, 'Financial Analyst')
            self.assertEqual(profile.years_of_experience, '3-5 years')

            skills = {s.skill_name: s.proficiency_level for s in user.skills}
            self.assertIn('Excel', skills)
            self.assertIn('Statistics', skills)

    def test_returning_after_break_registration(self):
        """Test registration as Returning After Career Break captures break duration and prior role."""
        res = self.client.post('/register', data={
            'full_name': 'Priya Return',
            'email': 'priya.return@example.com',
            'password': 'Password123!',
            'target_role': 'Full Stack Developer',
            'current_status': 'Returning After Career Break',
            'break_previous_role': 'Senior Java Developer',
            'break_experience_years': '5+ years',
            'break_duration': '1-2 years',
            'break_skills': 'Java, Spring Boot, MySQL'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Welcome to CareerSkill AI,", html)

        with self.app.app_context():
            user = User.query.filter_by(email='priya.return@example.com').first()
            self.assertIsNotNone(user)
            profile = user.user_profile
            self.assertEqual(profile.current_status, 'Returning After Career Break')
            self.assertEqual(profile.previous_role, 'Senior Java Developer')
            self.assertEqual(profile.break_duration, '1-2 years')

            skills = {s.skill_name for s in user.skills}
            self.assertIn('Java', skills)
            self.assertIn('Spring Boot', skills)


if __name__ == '__main__':
    unittest.main()
