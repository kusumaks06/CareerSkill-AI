import os
import unittest
import tempfile
import sqlite3
from werkzeug.security import generate_password_hash
from sqlalchemy import inspect
from app import create_app
from models import db, User, UserProfile, TargetCareer
from services.db_migrator import migrate_database_schema


class TestDatabaseMigration(unittest.TestCase):
    """Test suite verifying safe SQLite schema migrations, column additions, and data preservation."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.temp_db_fd)
        self.db_uri = f"sqlite:///{self.temp_db_path}"

        # Initialize SQLite database with an older schema without is_admin, is_active, role
        conn = sqlite3.connect(self.temp_db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(256),
                created_at DATETIME
            )
        """)
        # Insert test users with old schema
        cur.execute("""
            INSERT INTO users (full_name, email, password_hash)
            VALUES ('Legacy User', 'legacy@example.com', ?)
        """, (generate_password_hash('LegacyPass123!'),))
        conn.commit()
        conn.close()

        # Create test app configured to use the legacy SQLite DB file
        self.app = create_app('testing', test_config={'SQLALCHEMY_DATABASE_URI': self.db_uri})
        self.client = self.app.test_client()
        with self.app.app_context():
            migrate_database_schema(db, self.app, seed_admin=True)

    def tearDown(self):
        os.environ.pop('DATABASE_URL', None)
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except OSError:
                pass

    def test_schema_migration_adds_missing_columns(self):
        """Verify that migrate_database_schema safely adds is_admin, is_active, and role."""
        with self.app.app_context():
            migrate_database_schema(db, self.app)

            inspector = inspect(db.engine)
            columns = {col['name'] for col in inspector.get_columns('users')}

            self.assertIn('is_admin', columns)
            self.assertIn('is_active', columns)
            self.assertIn('role', columns)
            self.assertIn('first_login', columns)

    def test_existing_user_data_is_preserved_and_defaults_applied(self):
        """Verify that existing users are preserved and assigned safe default roles."""
        with self.app.app_context():
            migrate_database_schema(db, self.app)

            legacy_user = User.query.filter_by(email='legacy@example.com').first()
            self.assertIsNotNone(legacy_user)
            self.assertEqual(legacy_user.full_name, 'Legacy User')
            self.assertFalse(legacy_user.is_admin)
            self.assertTrue(legacy_user.is_active)
            self.assertEqual(legacy_user.role, 'user')
            self.assertFalse(legacy_user.first_login)
            self.assertTrue(legacy_user.check_password('LegacyPass123!'))

    def test_admin_seeding_creates_admin_if_none_exists(self):
        """Verify that default platform admin is created when no admin account is present."""
        with self.app.app_context():
            migrate_database_schema(db, self.app)

            admin_user = User.query.filter_by(email='admin@careerskill.ai').first()
            self.assertIsNotNone(admin_user)
            self.assertTrue(admin_user.is_admin)
            self.assertTrue(admin_user.is_active)
            self.assertEqual(admin_user.role, 'admin')
            self.assertTrue(admin_user.check_password('AdminMaster2026!'))

    def test_idempotent_migrations(self):
        """Verify that running migrate_database_schema multiple times causes no errors or duplicates."""
        with self.app.app_context():
            migrate_database_schema(db, self.app)
            migrate_database_schema(db, self.app)

            user_count = User.query.filter_by(email='legacy@example.com').count()
            self.assertEqual(user_count, 1)

            admin_count = User.query.filter_by(email='admin@careerskill.ai').count()
            self.assertEqual(admin_count, 1)

    def test_legacy_user_can_login_and_access_dashboard(self):
        """Verify that legacy users can log in with their existing passwords and view their dashboard."""
        resp = self.client.post('/login', data={
            'email': 'legacy@example.com',
            'password': 'LegacyPass123!'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Legacy User', html)

    def test_admin_user_can_login_and_access_admin_dashboard(self):
        """Verify that admin users can log in and view the admin dashboard."""
        resp = self.client.post('/login', data={
            'email': 'admin@careerskill.ai',
            'password': 'AdminMaster2026!'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        admin_dash_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_dash_resp.status_code, 200)
        self.assertIn('Admin Dashboard', admin_dash_resp.get_data(as_text=True))

    def test_normal_user_cannot_access_admin_dashboard(self):
        """Verify that normal users are forbidden from accessing admin routes."""
        # Login as normal legacy user
        self.client.post('/login', data={
            'email': 'legacy@example.com',
            'password': 'LegacyPass123!'
        }, follow_redirects=True)

        admin_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_resp.status_code, 403)


if __name__ == '__main__':
    unittest.main()
