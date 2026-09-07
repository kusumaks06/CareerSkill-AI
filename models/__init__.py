"""Models package for CareerSkill AI SQLAlchemy database entities."""
from models.user import (
    db, 
    User, 
    CareerProfile, 
    UserProfile, 
    UserSkill, 
    TargetCareer,
    PasswordResetOTP,
    SkillGapAnalysis,
    SkillGapItem,
    PROFICIENCY_SCORE_MAP
)
from models.course import (
    Course,
    UserCourseRecommendation,
    CourseFeedback
)
from models.roadmap import (
    UserRoadmap,
    RoadmapMilestone
)
from models.assessment import (
    AssessmentQuestion,
    AssessmentAttempt,
    AssessmentAnswer
)
from models.progress import (
    CourseProgress,
    LearningActivity,
    SkillProgressHistory
)
from models.suggestion import (
    Suggestion
)
from models.career_market import (
    CustomCareer,
    SkillDefinition,
    MarketRequirement,
    AdminActivityLog
)

__all__ = [
    'db', 
    'User', 
    'CareerProfile', 
    'UserProfile', 
    'UserSkill', 
    'TargetCareer',
    'PasswordResetOTP',
    'SkillGapAnalysis',
    'SkillGapItem',
    'PROFICIENCY_SCORE_MAP',
    'Course',
    'UserCourseRecommendation',
    'CourseFeedback',
    'UserRoadmap',
    'RoadmapMilestone',
    'AssessmentQuestion',
    'AssessmentAttempt',
    'AssessmentAnswer',
    'CourseProgress',
    'LearningActivity',
    'SkillProgressHistory',
    'Suggestion',
    'CustomCareer',
    'SkillDefinition',
    'MarketRequirement',
    'AdminActivityLog'
]

