import json
from datetime import datetime, timezone
from models.user import db, get_utc_now


class CustomCareer(db.Model):
    """Admin-managed Career Pathway entity supporting dynamic career additions and edits."""
    __tablename__ = 'custom_careers'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, unique=True, index=True)
    normalized_title = db.Column(db.String(150), nullable=False, index=True)
    category = db.Column(db.String(100), default='Technology')
    description = db.Column(db.Text, nullable=True)

    core_skills_json = db.Column(db.Text, nullable=True)  # JSON list of primary skills
    secondary_skills_json = db.Column(db.Text, nullable=True)  # JSON list of secondary skills
    domain_keywords_json = db.Column(db.Text, nullable=True)  # JSON list of domain keywords
    tools_json = db.Column(db.Text, nullable=True)  # JSON list of tools/technologies

    experience_level = db.Column(db.String(80), default='All Experience Levels')
    salary_range = db.Column(db.String(100), default='₹6,00,000 - ₹15,00,000 / yr')
    market_demand = db.Column(db.String(80), default='High Demand')

    priority = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    @property
    def core_skills(self):
        if not self.core_skills_json:
            return []
        try:
            return json.loads(self.core_skills_json)
        except Exception:
            return [s.strip() for s in self.core_skills_json.split(',') if s.strip()]

    @core_skills.setter
    def core_skills(self, value):
        if isinstance(value, list):
            self.core_skills_json = json.dumps(value)
        elif isinstance(value, str):
            self.core_skills_json = json.dumps([s.strip() for s in value.split(',') if s.strip()])

    @property
    def secondary_skills(self):
        if not self.secondary_skills_json:
            return []
        try:
            return json.loads(self.secondary_skills_json)
        except Exception:
            return [s.strip() for s in self.secondary_skills_json.split(',') if s.strip()]

    @secondary_skills.setter
    def secondary_skills(self, value):
        if isinstance(value, list):
            self.secondary_skills_json = json.dumps(value)
        elif isinstance(value, str):
            self.secondary_skills_json = json.dumps([s.strip() for s in value.split(',') if s.strip()])

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'normalized_title': self.normalized_title,
            'category': self.category,
            'description': self.description or '',
            'core_skills': self.core_skills,
            'secondary_skills': self.secondary_skills,
            'experience_level': self.experience_level or 'All Experience Levels',
            'salary_range': self.salary_range or '₹6,00,000 - ₹15,00,000 / yr',
            'market_demand': self.market_demand or 'High Demand',
            'priority': self.priority,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime("%d %b %Y") if self.created_at else None
        }


class SkillDefinition(db.Model):
    """Admin-managed Canonical Skill entity."""
    __tablename__ = 'skill_definitions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    category = db.Column(db.String(80), default='Technical')  # Technical, Analytics, Soft Skills, Domain
    description = db.Column(db.Text, nullable=True)
    topics_json = db.Column(db.Text, nullable=True)  # JSON list of syllabus topics
    difficulty = db.Column(db.String(50), default='Moderate')  # Easy, Moderate, Difficult
    demand_status = db.Column(db.String(50), default='In-Demand')  # In-Demand, Emerging, Stable, Outdated
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    @property
    def topics(self):
        if not self.topics_json:
            return []
        try:
            return json.loads(self.topics_json)
        except Exception:
            return [t.strip() for t in self.topics_json.split(',') if t.strip()]

    @topics.setter
    def topics(self, value):
        if isinstance(value, list):
            self.topics_json = json.dumps(value)
        elif isinstance(value, str):
            self.topics_json = json.dumps([t.strip() for t in value.split(',') if t.strip()])

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'description': self.description or '',
            'topics': self.topics,
            'difficulty': self.difficulty,
            'demand_status': self.demand_status or 'In-Demand',
            'is_active': self.is_active,
            'created_at': self.created_at.strftime("%d %b %Y") if self.created_at else None
        }


class MarketRequirement(db.Model):
    """Admin-managed labor market skill requirement benchmark."""
    __tablename__ = 'market_requirements'

    id = db.Column(db.Integer, primary_key=True)
    career_title = db.Column(db.String(150), nullable=False, index=True)
    skill_name = db.Column(db.String(120), nullable=False, index=True)
    required_level = db.Column(db.String(50), default='Intermediate')  # Beginner, Intermediate, Advanced, Expert
    importance = db.Column(db.String(50), default='Important')  # Critical, Important, Useful, Optional
    experience_level = db.Column(db.String(80), default='Entry to Mid-Level')
    salary_range = db.Column(db.String(100), default='Industry Benchmark')
    market_demand = db.Column(db.String(80), default='High Demand')
    topics_json = db.Column(db.Text, nullable=True)
    estimated_hours = db.Column(db.Float, default=20.0)
    difficulty = db.Column(db.String(50), default='Moderate')
    source_reference = db.Column(db.String(255), default='Industry Job Postings Analysis (2026)')
    is_verified = db.Column(db.Boolean, default=True)  # True = Verified Data, False = Estimated Data

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    @property
    def topics(self):
        if not self.topics_json:
            return []
        try:
            return json.loads(self.topics_json)
        except Exception:
            return [t.strip() for t in self.topics_json.split(',') if t.strip()]

    @topics.setter
    def topics(self, value):
        if isinstance(value, list):
            self.topics_json = json.dumps(value)
        elif isinstance(value, str):
            self.topics_json = json.dumps([t.strip() for t in value.split(',') if t.strip()])

    def to_dict(self):
        return {
            'id': self.id,
            'career_title': self.career_title,
            'skill_name': self.skill_name,
            'required_level': self.required_level,
            'importance': self.importance,
            'experience_level': self.experience_level or 'Entry to Mid-Level',
            'salary_range': self.salary_range or 'Industry Benchmark',
            'market_demand': self.market_demand or 'High Demand',
            'topics': self.topics,
            'estimated_hours': round(self.estimated_hours, 1),
            'difficulty': self.difficulty,
            'source_reference': self.source_reference,
            'is_verified': self.is_verified,
            'data_type': 'Verified Data' if self.is_verified else 'Estimated Data',
            'updated_at': self.updated_at.strftime("%d %b %Y") if self.updated_at else None
        }


class AdminActivityLog(db.Model):
    """Audit log tracking administrative governance actions and modifications."""
    __tablename__ = 'admin_activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    admin_name = db.Column(db.String(120), default='Administrator')
    action = db.Column(db.String(100), nullable=False)  # e.g., "Create Course", "Delete User"
    target_type = db.Column(db.String(80), nullable=True)  # "User", "Course", "Skill", "Market Requirement"
    target_name = db.Column(db.String(150), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    admin = db.relationship('User', backref=db.backref('admin_activity_records', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'admin_name': self.admin_name,
            'action': self.action,
            'target_type': self.target_type,
            'target_name': self.target_name,
            'details': self.details or '',
            'date': self.created_at.strftime("%d %b %Y, %H:%M") if self.created_at else None
        }
