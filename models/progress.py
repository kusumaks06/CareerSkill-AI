import json
from datetime import datetime, timezone, timedelta
from models.user import db, get_utc_now


class CourseProgress(db.Model):
    """Database model for tracking user progress across specific courses."""
    __tablename__ = 'course_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False, index=True)
    
    status = db.Column(db.String(50), default='Not Started')  # Not Started, In Progress, Completed
    progress_percentage = db.Column(db.Integer, default=0)  # 0 - 100%
    hours_completed = db.Column(db.Float, default=0.0)
    total_hours = db.Column(db.Float, default=10.0)
    
    last_accessed_at = db.Column(db.DateTime, default=get_utc_now)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    course = db.relationship('Course', lazy=True)

    def update_progress(self, pct: int, hours: float = None, status: str = None):
        """Safely updates progress percentage, hours, and status."""
        self.progress_percentage = max(0, min(100, int(pct)))
        
        if hours is not None:
            self.hours_completed = max(0.0, float(hours))
        elif self.total_hours and self.total_hours > 0:
            self.hours_completed = round((self.progress_percentage / 100.0) * self.total_hours, 1)

        if status:
            self.status = status
        else:
            if self.progress_percentage == 100:
                self.status = 'Completed'
            elif self.progress_percentage > 0:
                self.status = 'In Progress'
            else:
                self.status = 'Not Started'

        self.last_accessed_at = get_utc_now()

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'course_id': self.course_id,
            'status': self.status,
            'progress_percentage': self.progress_percentage,
            'hours_completed': round(self.hours_completed, 1),
            'total_hours': round(self.total_hours, 1),
            'course_title': self.course.title if self.course else 'Course',
            'skill': self.course.skill if self.course else 'General',
            'last_accessed_at': self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<CourseProgress user={self.user_id} course={self.course_id} progress={self.progress_percentage}% status='{self.status}'>"


class LearningActivity(db.Model):
    """Database model for chronological audit trail of all learning activities."""
    __tablename__ = 'learning_activities'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    activity_type = db.Column(db.String(50), nullable=False)  # Course, Roadmap, Assessment, Study Session
    title = db.Column(db.String(255), nullable=False)
    skill = db.Column(db.String(120), nullable=False, index=True)
    
    hours = db.Column(db.Float, default=0.0)
    score = db.Column(db.Float, nullable=True)  # Assessment score or quiz score if applicable
    progress_delta = db.Column(db.Float, default=0.0)  # e.g., +5.0%
    notes = db.Column(db.Text, nullable=True)
    
    activity_date = db.Column(db.DateTime, default=get_utc_now, index=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'activity_type': self.activity_type,
            'title': self.title,
            'skill': self.skill,
            'hours': round(self.hours, 1),
            'score': round(self.score, 1) if self.score is not None else None,
            'progress_delta': round(self.progress_delta, 1) if self.progress_delta else None,
            'notes': self.notes,
            'activity_date': self.activity_date.strftime("%d %b %Y, %H:%M") if self.activity_date else None,
            'date_short': self.activity_date.strftime("%d %b") if self.activity_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<LearningActivity {self.id}: User {self.user_id} - {self.activity_type} '{self.title}' ({self.hours}h)>"


class SkillProgressHistory(db.Model):
    """Database model for tracking skill proficiency evolution over time."""
    __tablename__ = 'skill_progress_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    skill_name = db.Column(db.String(120), nullable=False, index=True)
    
    previous_score = db.Column(db.Integer, default=0)  # 0-100%
    current_score = db.Column(db.Integer, default=25)   # 0-100%
    target_score = db.Column(db.Integer, default=75)    # 0-100%
    
    triggered_by = db.Column(db.String(80), default='Assessment')  # Onboarding, Assessment, Course Completion, Roadmap Milestone
    recorded_at = db.Column(db.DateTime, default=get_utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'skill_name': self.skill_name,
            'previous_score': self.previous_score,
            'current_score': self.current_score,
            'target_score': self.target_score,
            'improvement': self.current_score - self.previous_score,
            'remaining_gap': max(0, self.target_score - self.current_score),
            'triggered_by': self.triggered_by,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None
        }

    def __repr__(self):
        return f"<SkillProgressHistory user={self.user_id} skill='{self.skill_name}' {self.previous_score}% -> {self.current_score}% (Target {self.target_score}%)>"
