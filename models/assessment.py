import json
from datetime import datetime, timezone
from models.user import db, get_utc_now


class AssessmentQuestion(db.Model):
    """Database model for curated skill assessment questions."""
    __tablename__ = 'assessment_questions'

    id = db.Column(db.Integer, primary_key=True)
    skill = db.Column(db.String(120), nullable=False, index=True)  # e.g., 'SQL', 'Python', 'Excel', 'Power BI'
    topic = db.Column(db.String(150), nullable=False, index=True)  # e.g., 'INNER, LEFT & RIGHT JOINs'
    difficulty = db.Column(db.String(50), default='Intermediate')  # Beginner, Intermediate, Advanced
    question_type = db.Column(db.String(50), default='multiple_choice')  # multiple_choice, true_false, practical
    question_text = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text, nullable=False)  # Serialized JSON list of choice strings
    correct_answer = db.Column(db.String(500), nullable=False)
    explanation = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def set_options(self, options_list):
        self.options_json = json.dumps(options_list or [])

    def get_options(self):
        if not self.options_json:
            return []
        try:
            return json.loads(self.options_json)
        except Exception:
            return []

    def to_dict(self, include_correct=False):
        data = {
            'id': self.id,
            'skill': self.skill,
            'topic': self.topic,
            'difficulty': self.difficulty,
            'question_type': self.question_type,
            'question_text': self.question_text,
            'options': self.get_options()
        }
        if include_correct:
            data['correct_answer'] = self.correct_answer
            data['explanation'] = self.explanation
        return data

    def __repr__(self):
        return f"<AssessmentQuestion {self.id}: {self.skill} - {self.topic} ({self.difficulty})>"


class AssessmentAttempt(db.Model):
    """Database model for a user's skill assessment session."""
    __tablename__ = 'assessment_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    skill_name = db.Column(db.String(120), nullable=False, index=True)
    target_role = db.Column(db.String(120), nullable=True, default='Data Analyst')
    difficulty = db.Column(db.String(50), default='Intermediate')
    
    total_questions = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    incorrect_count = db.Column(db.Integer, default=0)
    score = db.Column(db.Float, default=0.0)  # Percentage 0-100

    # Three-way comparison levels and scores
    self_reported_level = db.Column(db.String(50), default='Beginner')
    self_reported_score = db.Column(db.Integer, default=25)
    assessed_level = db.Column(db.String(50), default='Beginner')
    assessed_score = db.Column(db.Integer, default=25)
    market_required_level = db.Column(db.String(50), default='Intermediate')
    market_required_score = db.Column(db.Integer, default=50)
    comparison_verdict = db.Column(db.Text, nullable=True)

    # Retake tracking
    previous_score = db.Column(db.Float, nullable=True)
    score_improvement = db.Column(db.Float, nullable=True)  # e.g., +33.0%

    # Topic breakdown
    strong_topics_json = db.Column(db.Text, nullable=True)
    weak_topics_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=get_utc_now)

    # Relationships
    answers = db.relationship(
        'AssessmentAnswer', 
        backref='attempt', 
        lazy=True, 
        cascade="all, delete-orphan",
        order_by="AssessmentAnswer.id"
    )

    def set_strong_topics(self, topics_list):
        self.strong_topics_json = json.dumps(topics_list or [])

    def get_strong_topics(self):
        if not self.strong_topics_json:
            return []
        try:
            return json.loads(self.strong_topics_json)
        except Exception:
            return []

    def set_weak_topics(self, topics_list):
        self.weak_topics_json = json.dumps(topics_list or [])

    def get_weak_topics(self):
        if not self.weak_topics_json:
            return []
        try:
            return json.loads(self.weak_topics_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'skill_name': self.skill_name,
            'target_role': self.target_role,
            'difficulty': self.difficulty,
            'total_questions': self.total_questions,
            'correct_count': self.correct_count,
            'incorrect_count': self.incorrect_count,
            'score': round(self.score, 1),
            'self_reported_level': self.self_reported_level,
            'self_reported_score': self.self_reported_score,
            'assessed_level': self.assessed_level,
            'assessed_score': self.assessed_score,
            'market_required_level': self.market_required_level,
            'market_required_score': self.market_required_score,
            'comparison_verdict': self.comparison_verdict,
            'previous_score': round(self.previous_score, 1) if self.previous_score is not None else None,
            'score_improvement': round(self.score_improvement, 1) if self.score_improvement is not None else None,
            'strong_topics': self.get_strong_topics(),
            'weak_topics': self.get_weak_topics(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'answers': [a.to_dict() for a in self.answers]
        }

    def __repr__(self):
        return f"<AssessmentAttempt {self.id}: User {self.user_id} - {self.skill_name} ({self.score}%)>"


class AssessmentAnswer(db.Model):
    """Database model for individual question answers within an assessment attempt."""
    __tablename__ = 'assessment_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('assessment_attempts.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('assessment_questions.id'), nullable=True)
    topic = db.Column(db.String(150), nullable=False)
    user_answer = db.Column(db.String(500), nullable=True)
    correct_answer = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    # Relationship to question
    question = db.relationship('AssessmentQuestion', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'attempt_id': self.attempt_id,
            'question_id': self.question_id,
            'topic': self.topic,
            'user_answer': self.user_answer,
            'correct_answer': self.correct_answer,
            'is_correct': self.is_correct,
            'question': self.question.to_dict(include_correct=True) if self.question else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<AssessmentAnswer {self.id}: Attempt {self.attempt_id} - Correct={self.is_correct}>"
