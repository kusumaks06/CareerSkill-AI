from datetime import datetime, timezone
from models.user import db, get_utc_now


class Suggestion(db.Model):
    """
    Database model for user suggestions, platform feedback, and content enhancement requests.
    Supports user tracking, status transitions, and administrative review responses.
    """
    __tablename__ = 'suggestions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Categories: Missing Career, Missing Skill, Missing Course,
    # Incorrect Recommendation, Incorrect Market Information, Roadmap Suggestion, General Suggestion
    category = db.Column(db.String(100), nullable=False)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)

    # Optional contextual targets
    career = db.Column(db.String(150), nullable=True)
    skill = db.Column(db.String(100), nullable=True)
    course = db.Column(db.String(255), nullable=True)

    # Status workflow: Submitted -> Under Review -> Resolved / Rejected
    status = db.Column(db.String(50), nullable=False, default='Submitted')

    # Administrative review
    admin_response = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.full_name if self.user else 'Learner',
            'user_email': self.user.email if self.user else '',
            'category': self.category,
            'title': self.title,
            'description': self.description,
            'career': self.career or '',
            'skill': self.skill or '',
            'course': self.course or '',
            'status': self.status,
            'admin_response': self.admin_response or '',
            'has_response': bool(self.admin_response and self.admin_response.strip()),
            'is_editable': self.status == 'Submitted',
            'created_at': self.created_at.strftime("%d %b %Y, %H:%M") if self.created_at else None,
            'created_at_iso': self.created_at.isoformat() if self.created_at else None,
            'date_formatted': self.created_at.strftime("%d %b %Y") if self.created_at else None,
            'updated_at': self.updated_at.strftime("%d %b %Y, %H:%M") if self.updated_at else None,
            'resolved_at': self.resolved_at.strftime("%d %b %Y, %H:%M") if self.resolved_at else None
        }

    def __repr__(self):
        return f"<Suggestion id={self.id} user={self.user_id} category='{self.category}' status='{self.status}'>"
