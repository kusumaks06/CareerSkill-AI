import json
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def get_utc_now():
    return datetime.now(timezone.utc)

# Numerical mapping for proficiency levels
PROFICIENCY_SCORE_MAP = {
    'Beginner': 25,
    'Intermediate': 50,
    'Advanced': 75,
    'Expert': 100,
    "I don't know this skill": 0,
    'No Knowledge': 0
}

class User(db.Model):
    """User entity for authentication and profile management."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    role = db.Column(db.String(50), default='user', nullable=False)  # 'admin' or 'user'
    first_login = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    # Relationships
    profiles = db.relationship('CareerProfile', backref='user', lazy=True, cascade="all, delete-orphan")
    user_profile = db.relationship('UserProfile', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")
    skills = db.relationship('UserSkill', backref='user', lazy=True, cascade="all, delete-orphan")
    target_careers = db.relationship('TargetCareer', backref='user', lazy=True, cascade="all, delete-orphan")
    reset_otps = db.relationship('PasswordResetOTP', backref='user', lazy=True, cascade="all, delete-orphan")
    gap_analyses = db.relationship('SkillGapAnalysis', backref='user', lazy=True, cascade="all, delete-orphan")
    assessment_attempts = db.relationship('AssessmentAttempt', backref='user', lazy=True, cascade="all, delete-orphan")
    course_progress = db.relationship('CourseProgress', backref='user', lazy=True, cascade="all, delete-orphan")
    learning_activities = db.relationship('LearningActivity', backref='user', lazy=True, cascade="all, delete-orphan")
    skill_progress_history = db.relationship('SkillProgressHistory', backref='user', lazy=True, cascade="all, delete-orphan")
    feedbacks = db.relationship('CourseFeedback', backref='user', lazy=True, cascade="all, delete-orphan")
    suggestions = db.relationship('Suggestion', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        """Hashes and sets the password."""
        if password:
            self.password_hash = generate_password_hash(password)
        else:
            self.password_hash = None

    def check_password(self, password):
        """Verifies the hashed password."""
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class PasswordResetOTP(db.Model):
    """Stores hashed 6-digit OTPs for password resets."""
    __tablename__ = 'password_reset_otps'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    otp_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    verified = db.Column(db.Boolean, default=False)
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def set_otp(self, otp_str):
        """Hashes and stores the OTP."""
        self.otp_hash = generate_password_hash(str(otp_str))

    def check_otp(self, otp_str):
        """Verifies candidate OTP against stored hash."""
        if not self.otp_hash or not otp_str:
            return False
        return check_password_hash(self.otp_hash, str(otp_str).strip())

    def is_expired(self):
        """Checks if the OTP has exceeded its 10-minute validity."""
        if not self.expires_at:
            return True
        if self.expires_at.tzinfo is None:
            exp = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            exp = self.expires_at
        return datetime.now(timezone.utc) > exp

    def is_valid(self):
        """Checks if OTP is unverified, unexpired, and under attempt threshold."""
        return not self.verified and not self.is_expired() and self.attempts < 5

    def __repr__(self):
        return f"<PasswordResetOTP user={self.user_id} verified={self.verified}>"


class UserProfile(db.Model):
    """Complete career onboarding and background profile."""
    __tablename__ = 'user_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Step 1: Education & Background
    education = db.Column(db.String(120), nullable=True)
    degree = db.Column(db.String(120), nullable=True)
    branch = db.Column(db.String(150), nullable=True)
    graduation_year = db.Column(db.String(20), nullable=True)
    current_status = db.Column(db.String(80), nullable=True)
    current_semester_year = db.Column(db.String(80), nullable=True)

    # Step 2: Experience & Work Details
    current_job_role = db.Column(db.String(150), nullable=True)
    previous_role = db.Column(db.String(150), nullable=True)
    years_of_experience = db.Column(db.String(80), nullable=True)
    break_duration = db.Column(db.String(80), nullable=True)
    existing_skills = db.Column(db.Text, nullable=True)
    experience_level = db.Column(db.String(80), nullable=True)
    has_project_experience = db.Column(db.Boolean, default=False)
    project_experience = db.Column(db.Text, nullable=True)

    # Step 4: Learning Schedule
    learning_hours_per_day = db.Column(db.String(50), nullable=True)
    learning_days_per_week = db.Column(db.Integer, default=5)
    learning_hours_per_week = db.Column(db.Float, default=10.0)

    # Step 5: Learning Preferences
    learning_preference_json = db.Column(db.Text, nullable=True)
    preferred_difficulty = db.Column(db.String(50), default='Balanced')

    # Step 6: Career Goals
    career_goal_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    def set_learning_preferences(self, prefs):
        self.learning_preference_json = json.dumps(prefs or [])

    def get_learning_preferences(self):
        if not self.learning_preference_json:
            return []
        try:
            return json.loads(self.learning_preference_json)
        except Exception:
            return []

    def set_career_goals(self, goals):
        self.career_goal_json = json.dumps(goals or [])

    def get_career_goals(self):
        if not self.career_goal_json:
            return []
        try:
            return json.loads(self.career_goal_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'education': self.education,
            'degree': self.degree,
            'branch': self.branch,
            'graduation_year': self.graduation_year,
            'current_status': self.current_status,
            'current_semester_year': self.current_semester_year,
            'current_job_role': self.current_job_role,
            'previous_role': self.previous_role,
            'years_of_experience': self.years_of_experience,
            'break_duration': self.break_duration,
            'existing_skills': self.existing_skills,
            'experience_level': self.experience_level,
            'has_project_experience': self.has_project_experience,
            'project_experience': self.project_experience,
            'learning_hours_per_day': self.learning_hours_per_day,
            'learning_days_per_week': self.learning_days_per_week,
            'learning_hours_per_week': self.learning_hours_per_week,
            'learning_preferences': self.get_learning_preferences(),
            'preferred_difficulty': self.preferred_difficulty,
            'career_goals': self.get_career_goals(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class UserSkill(db.Model):
    """User's current self-reported skills with proficiency & confidence."""
    __tablename__ = 'user_skills'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    skill_id = db.Column(db.String(100), nullable=True)
    skill_name = db.Column(db.String(120), nullable=False)
    proficiency_level = db.Column(db.String(50), nullable=False, default='Beginner')
    proficiency_score = db.Column(db.Integer, nullable=False, default=25)
    confidence_level = db.Column(db.Integer, nullable=False, default=3)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    def set_proficiency(self, level):
        """Sets both human level name and internal numerical score."""
        self.proficiency_level = level
        self.proficiency_score = PROFICIENCY_SCORE_MAP.get(level, 25)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'skill_name': self.skill_name,
            'proficiency_level': self.proficiency_level,
            'proficiency_score': self.proficiency_score,
            'confidence_level': self.confidence_level
        }


class TargetCareer(db.Model):
    """Stores the user's selected or custom target career role."""
    __tablename__ = 'target_careers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    career_name = db.Column(db.String(150), nullable=False)
    normalized_career_name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'career_name': self.career_name,
            'normalized_career_name': self.normalized_career_name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CareerProfile(db.Model):
    """Stores user's target career role, market requirements, and skill analysis."""
    __tablename__ = 'career_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    target_role = db.Column(db.String(150), nullable=False)
    normalized_role = db.Column(db.String(150), nullable=False)
    is_custom_role = db.Column(db.Boolean, default=False)
    confidence_score = db.Column(db.Integer, default=100)
    market_status = db.Column(db.String(100), default='Verified Industry Benchmark')
    explanation = db.Column(db.Text, nullable=True)
    
    # Serialized JSON lists
    matched_skills_json = db.Column(db.Text, nullable=True)
    related_roles_json = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def set_skills(self, skills_list):
        self.matched_skills_json = json.dumps(skills_list or [])

    def get_skills(self):
        if not self.matched_skills_json:
            return []
        try:
            return json.loads(self.matched_skills_json)
        except Exception:
            return []

    def set_related_roles(self, roles_list):
        self.related_roles_json = json.dumps(roles_list or [])

    def get_related_roles(self):
        if not self.related_roles_json:
            return []
        try:
            return json.loads(self.related_roles_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'target_role': self.target_role,
            'normalized_role': self.normalized_role,
            'is_custom_role': self.is_custom_role,
            'confidence_score': self.confidence_score,
            'market_status': self.market_status,
            'explanation': self.explanation,
            'matched_skills': self.get_skills(),
            'related_roles': self.get_related_roles(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<CareerProfile {self.target_role} ({self.market_status})>"


class SkillGapAnalysis(db.Model):
    """Stores full skill gap analysis snapshots for users and target careers."""
    __tablename__ = 'skill_gap_analyses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_role = db.Column(db.String(150), nullable=False)
    normalized_role = db.Column(db.String(150), nullable=False)
    is_custom_role = db.Column(db.Boolean, default=False)
    market_status = db.Column(db.String(100), default='Verified Industry Benchmark')
    
    # Aggregated metrics
    readiness_score = db.Column(db.Integer, default=0)  # 0 to 100
    total_learning_hours = db.Column(db.Integer, default=0)
    estimated_weeks = db.Column(db.Integer, default=0)
    completion_date_str = db.Column(db.String(50), nullable=True)
    
    strong_count = db.Column(db.Integer, default=0)
    partial_count = db.Column(db.Integer, default=0)
    missing_count = db.Column(db.Integer, default=0)
    
    explanation = db.Column(db.Text, nullable=True)
    topic_evaluations_json = db.Column(db.Text, nullable=True)
    recommendations_json = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    items = db.relationship('SkillGapItem', backref='analysis', lazy=True, cascade="all, delete-orphan")

    def set_topic_evaluations(self, data):
        self.topic_evaluations_json = json.dumps(data or {})

    def get_topic_evaluations(self):
        if not self.topic_evaluations_json:
            return {}
        try:
            return json.loads(self.topic_evaluations_json)
        except Exception:
            return {}

    def set_recommendations(self, data):
        self.recommendations_json = json.dumps(data or [])

    def get_recommendations(self):
        if not self.recommendations_json:
            return []
        try:
            return json.loads(self.recommendations_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'target_role': self.target_role,
            'normalized_role': self.normalized_role,
            'is_custom_role': self.is_custom_role,
            'market_status': self.market_status,
            'readiness_score': self.readiness_score,
            'total_learning_hours': self.total_learning_hours,
            'estimated_weeks': self.estimated_weeks,
            'completion_date': self.completion_date_str,
            'strong_count': self.strong_count,
            'partial_count': self.partial_count,
            'missing_count': self.missing_count,
            'explanation': self.explanation,
            'recommendations': self.get_recommendations(),
            'items': [item.to_dict() for item in self.items]
        }


class SkillGapItem(db.Model):
    """Detailed item for each required skill vs user skill comparison."""
    __tablename__ = 'skill_gap_items'

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('skill_gap_analyses.id'), nullable=False)
    
    skill_name = db.Column(db.String(120), nullable=False)
    normalized_skill_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), default='Technical')
    importance = db.Column(db.String(50), default='High')
    importance_weight = db.Column(db.Integer, default=3)
    
    required_level = db.Column(db.String(50), default='Intermediate')
    required_score = db.Column(db.Integer, default=50)
    
    user_level = db.Column(db.String(50), default='No Knowledge')
    user_score = db.Column(db.Integer, default=0)
    gap_score = db.Column(db.Integer, default=50)
    
    status = db.Column(db.String(50), default='MISSING')  # STRONG, PARTIAL, MISSING, LOW_PRIORITY
    priority = db.Column(db.String(50), default='High')  # Critical, High, Medium, Low
    difficulty = db.Column(db.String(50), default='Moderate')  # Easy, Moderate, Difficult
    
    estimated_hours = db.Column(db.Integer, default=40)
    remaining_hours = db.Column(db.Integer, default=40)
    
    all_topics_json = db.Column(db.Text, nullable=True)
    known_topics_json = db.Column(db.Text, nullable=True)
    remaining_topics_json = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def set_all_topics(self, topics):
        self.all_topics_json = json.dumps(topics or [])

    def get_all_topics(self):
        if not self.all_topics_json:
            return []
        try:
            return json.loads(self.all_topics_json)
        except Exception:
            return []

    def set_known_topics(self, topics):
        self.known_topics_json = json.dumps(topics or [])

    def get_known_topics(self):
        if not self.known_topics_json:
            return []
        try:
            return json.loads(self.known_topics_json)
        except Exception:
            return []

    def set_remaining_topics(self, topics):
        self.remaining_topics_json = json.dumps(topics or [])

    def get_remaining_topics(self):
        if not self.remaining_topics_json:
            return []
        try:
            return json.loads(self.remaining_topics_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'skill_name': self.skill_name,
            'normalized_skill_name': self.normalized_skill_name,
            'category': self.category,
            'importance': self.importance,
            'importance_weight': self.importance_weight,
            'required_level': self.required_level,
            'required_score': self.required_score,
            'user_level': self.user_level,
            'user_score': self.user_score,
            'gap_score': self.gap_score,
            'status': self.status,
            'priority': self.priority,
            'difficulty': self.difficulty,
            'estimated_hours': self.estimated_hours,
            'remaining_hours': self.remaining_hours,
            'all_topics': self.get_all_topics(),
            'known_topics': self.get_known_topics(),
            'remaining_topics': self.get_remaining_topics()
        }

