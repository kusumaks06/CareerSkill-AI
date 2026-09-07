import json
from datetime import datetime, timezone
from models.user import db, get_utc_now

class UserRoadmap(db.Model):
    """Database model for personalized multi-week learning roadmaps."""
    __tablename__ = 'user_roadmaps'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    target_role = db.Column(db.String(120), nullable=False, default='Data Analyst')
    total_weeks = db.Column(db.Integer, default=12)
    total_hours = db.Column(db.Float, default=120.0)
    weekly_hours = db.Column(db.Float, default=10.0)
    completion_percentage = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='In Progress')  # In Progress, Completed, Paused

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    milestones = db.relationship(
        'RoadmapMilestone', 
        backref='roadmap', 
        lazy=True, 
        cascade="all, delete-orphan",
        order_by="RoadmapMilestone.phase_number, RoadmapMilestone.week_start"
    )

    def calculate_progress(self):
        """Calculates current completion percentage based on milestone tasks and status."""
        if not self.milestones:
            self.completion_percentage = 0
            return 0

        total_tasks = 0
        completed_tasks = 0

        for m in self.milestones:
            tasks = m.get_tasks()
            if tasks:
                total_tasks += len(tasks)
                completed_tasks += sum(1 for t in tasks if t.get('completed', False))
            else:
                total_tasks += 1
                if m.is_completed:
                    completed_tasks += 1

        if total_tasks == 0:
            pct = 0
        else:
            pct = int((completed_tasks / total_tasks) * 100)

        self.completion_percentage = min(100, max(0, pct))
        if self.completion_percentage == 100:
            self.status = 'Completed'
        return self.completion_percentage

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'target_role': self.target_role,
            'total_weeks': self.total_weeks,
            'total_hours': self.total_hours,
            'weekly_hours': self.weekly_hours,
            'completion_percentage': self.completion_percentage,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'milestones': [m.to_dict() for m in self.milestones]
        }

    def __repr__(self):
        return f"<UserRoadmap user={self.user_id} role='{self.target_role}' progress={self.completion_percentage}%>"


class RoadmapMilestone(db.Model):
    """Database model for structured milestone steps within a multi-week roadmap."""
    __tablename__ = 'roadmap_milestones'

    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(db.Integer, db.ForeignKey('user_roadmaps.id'), nullable=False, index=True)
    phase_number = db.Column(db.Integer, default=1)  # 1 to 5
    phase_name = db.Column(db.String(120), default='Foundations & Prerequisites')
    week_start = db.Column(db.Integer, default=1)
    week_end = db.Column(db.Integer, default=2)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    skill = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(50), default='High')  # Critical, High, Medium, Low
    estimated_hours = db.Column(db.Float, default=20.0)
    checkpoint_title = db.Column(db.String(255), nullable=True)
    checkpoint_description = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    tasks_json = db.Column(db.Text, nullable=True)
    recommended_resources_json = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def set_tasks(self, tasks_list):
        self.tasks_json = json.dumps(tasks_list or [])

    def get_tasks(self):
        if not self.tasks_json:
            return []
        try:
            return json.loads(self.tasks_json)
        except Exception:
            return []

    def set_resources(self, resources_list):
        self.recommended_resources_json = json.dumps(resources_list or [])

    def get_resources(self):
        if not self.recommended_resources_json:
            return []
        try:
            return json.loads(self.recommended_resources_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'roadmap_id': self.roadmap_id,
            'phase_number': self.phase_number,
            'phase_name': self.phase_name,
            'week_start': self.week_start,
            'week_end': self.week_end,
            'title': self.title,
            'description': self.description,
            'skill': self.skill,
            'priority': self.priority,
            'estimated_hours': self.estimated_hours,
            'checkpoint_title': self.checkpoint_title,
            'checkpoint_description': self.checkpoint_description,
            'is_completed': self.is_completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'tasks': self.get_tasks(),
            'recommended_resources': self.get_resources(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<RoadmapMilestone {self.id}: Phase {self.phase_number} Weeks {self.week_start}-{self.week_end} '{self.title}'>"
