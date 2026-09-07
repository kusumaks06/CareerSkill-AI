import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import inspect
from app import create_app
from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    CareerProfile,
    SkillGapAnalysis,
    SkillGapItem,
    Course,
    UserCourseRecommendation,
    UserRoadmap,
    RoadmapMilestone
)
from config import INSTANCE_DIR
from services.recommendation_service import recommendation_service
from services.assessment_service import assessment_service

def initialize_database():
    """Initializes SQLite database, verifies tables, and seeds initial curated courses and assessment questions."""
    print("==================================================")
    print("[*] Initializing CareerSkill AI Database...")
    print(f"[*] Target Directory: {INSTANCE_DIR}")
    print("==================================================")

    # Ensure instance directory exists
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    app = create_app('development')

    try:
        with app.app_context():
            # Create all tables if they do not exist
            db.create_all()
            
            # Inspect existing tables in database engine
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()

            print("[*] Detected Database Tables:")
            for t in tables:
                print(f"    - {t}")

            if 'users' in tables and 'courses' in tables and 'assessment_questions' in tables:
                print("\n[+] Verification PASSED: 'users', 'courses', and 'assessment_questions' tables are present.")
            else:
                print("\n[-] Verification WARNING: One or more critical tables were not detected.")

            # Seed courses if needed
            course_count = Course.query.count()
            print(f"[*] Curated Courses in Database: {course_count}")

            # Seed assessment questions
            q_count = assessment_service.seed_questions_if_empty()
            print(f"[*] Assessment Questions in Database: {q_count}")

            print("Database initialized successfully.")
            return True
    except Exception as e:
        print(f"\n[-] Error during database initialization: {e}")
        return False

if __name__ == '__main__':
    success = initialize_database()
    if not success:
        sys.exit(1)
