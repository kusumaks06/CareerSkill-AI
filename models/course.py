import json
from datetime import datetime, timezone
from models.user import db, get_utc_now

class Course(db.Model):
    """Database model for curated learning resources and courses."""
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(120), nullable=False)  # e.g., Coursera, Kaggle, freeCodeCamp, edX, Microsoft Learn, YouTube
    skill = db.Column(db.String(120), nullable=False, index=True)  # Primary canonical skill (e.g., 'SQL', 'Python')
    category = db.Column(db.String(80), default='Technical')  # Technical, Analytics, Soft Skills, Domain
    level = db.Column(db.String(50), default='Beginner')  # Beginner, Intermediate, Advanced, All Levels
    url = db.Column(db.String(500), nullable=False)
    duration_hours = db.Column(db.Float, default=10.0)
    difficulty = db.Column(db.String(50), default='Moderate')  # Easy, Moderate, Difficult
    rating = db.Column(db.Float, nullable=True)  # e.g., 4.8 or None if not available
    language = db.Column(db.String(50), default='English')
    is_free = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    resource_type = db.Column(db.String(50), default='Course')  # Course, Tutorial, Documentation, Practice, Project, Certification
    topics_json = db.Column(db.Text, nullable=True)  # Serialized list of topics covered
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    recommendations = db.relationship('UserCourseRecommendation', backref='course', lazy=True, cascade="all, delete-orphan")
    feedbacks = db.relationship('CourseFeedback', backref='course', lazy=True, cascade="all, delete-orphan")

    def set_topics(self, topics_list):
        self.topics_json = json.dumps(topics_list or [])

    def get_topics(self):
        if not self.topics_json:
            return []
        try:
            return json.loads(self.topics_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'provider': self.provider,
            'skill': self.skill,
            'category': self.category,
            'level': self.level,
            'url': self.url,
            'duration_hours': self.duration_hours,
            'difficulty': self.difficulty,
            'rating': self.rating,
            'language': self.language,
            'is_free': self.is_free,
            'is_active': self.is_active,
            'resource_type': self.resource_type,
            'topics': self.get_topics(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<Course {self.id}: {self.title} ({self.provider} - {self.skill})>"


class UserCourseRecommendation(db.Model):
    """Stores personalized gap-based course recommendations for users."""
    __tablename__ = 'user_course_recommendations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False, index=True)
    skill_gap_id = db.Column(db.Integer, nullable=True)
    
    recommendation_score = db.Column(db.Integer, default=80)  # 0 - 100%
    priority = db.Column(db.String(50), default='High')  # Critical, High, Medium, Low
    status = db.Column(db.String(50), default='Recommended')  # Recommended, In Progress, Completed, Skipped, Saved
    why_recommended = db.Column(db.Text, nullable=True)
    matched_topics_json = db.Column(db.Text, nullable=True)
    estimated_weeks = db.Column(db.Integer, default=1)
    
    recommended_at = db.Column(db.DateTime, default=get_utc_now)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def set_matched_topics(self, topics_list):
        self.matched_topics_json = json.dumps(topics_list or [])

    def get_matched_topics(self):
        if not self.matched_topics_json:
            return []
        try:
            return json.loads(self.matched_topics_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'course_id': self.course_id,
            'skill_gap_id': self.skill_gap_id,
            'recommendation_score': self.recommendation_score,
            'priority': self.priority,
            'status': self.status,
            'why_recommended': self.why_recommended,
            'matched_topics': self.get_matched_topics(),
            'estimated_weeks': self.estimated_weeks,
            'recommended_at': self.recommended_at.isoformat() if self.recommended_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'course': self.course.to_dict() if self.course else None
        }

    def __repr__(self):
        return f"<UserCourseRecommendation user={self.user_id} course={self.course_id} score={self.recommendation_score}% status={self.status}>"


class CourseFeedback(db.Model):
    """Database model for user feedback, ratings, and reviews on completed courses."""
    __tablename__ = 'course_feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False, index=True)

    rating = db.Column(db.Integer, nullable=False, default=5)  # 1–5 stars
    usefulness = db.Column(db.String(50), nullable=False, default='Very Useful')  # Very Useful, Useful, Partially Useful, Not Useful
    improved_skill = db.Column(db.String(50), nullable=False, default='Yes')  # Yes, Partially, No
    liked_aspects = db.Column(db.Text, nullable=True)  # What did you like?
    improvement_suggestions = db.Column(db.Text, nullable=True)  # What should be improved?
    would_recommend = db.Column(db.String(20), nullable=False, default='Yes')  # Yes, No

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    @property
    def skill_improvement(self):
        return self.improved_skill

    @skill_improvement.setter
    def skill_improvement(self, value):
        self.improved_skill = value

    @property
    def comments(self):
        return self.liked_aspects

    @comments.setter
    def comments(self, value):
        self.liked_aspects = value

    @property
    def recommendation(self):
        return self.would_recommend

    @recommendation.setter
    def recommendation(self, value):
        self.would_recommend = value

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'course_id': self.course_id,
            'rating': self.rating,
            'usefulness': self.usefulness,
            'improved_skill': self.improved_skill,
            'skill_improvement': self.improved_skill,
            'liked_aspects': self.liked_aspects or '',
            'comments': self.liked_aspects or '',
            'improvement_suggestions': self.improvement_suggestions or '',
            'would_recommend': self.would_recommend,
            'recommendation': self.would_recommend,
            'user_name': self.user.full_name if self.user else 'User',
            'user_email': self.user.email if self.user else '',
            'course_title': self.course.title if self.course else 'Course',
            'course_provider': self.course.provider if self.course else '',
            'course_skill': self.course.skill if self.course else '',
            'created_at': self.created_at.strftime("%d %b %Y, %H:%M") if self.created_at else None,
            'created_at_iso': self.created_at.isoformat() if self.created_at else None,
            'date_formatted': self.created_at.strftime("%d %b %Y") if self.created_at else None,
            'updated_at': self.updated_at.strftime("%d %b %Y, %H:%M") if self.updated_at else None
        }

    def __repr__(self):
        return f"<CourseFeedback user={self.user_id} course={self.course_id} rating={self.rating} stars usefulness='{self.usefulness}'>"

