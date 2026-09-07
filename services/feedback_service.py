import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from models import (
    db,
    User,
    Course,
    CourseFeedback,
    UserCourseRecommendation,
    CourseProgress
)
from services.progress_service import progress_service


class FeedbackService:
    """Service handling course feedback submission, validation, analytics, and admin reporting."""

    VALID_USEFULNESS = ['Very Useful', 'Useful', 'Partially Useful', 'Not Useful']
    VALID_SKILL_IMPROVED = ['Yes', 'Partially', 'No']
    VALID_RECOMMEND = ['Yes', 'No']

    def submit_or_update_feedback(
        self,
        user_id: int,
        course_id: int,
        rating: int = 5,
        usefulness: str = 'Very Useful',
        improved_skill: Optional[str] = None,
        liked_aspects: Optional[str] = None,
        improvement_suggestions: Optional[str] = None,
        would_recommend: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submits new course feedback or updates existing feedback for the (user_id, course_id) pair.
        Prevents duplicate feedback entries and synchronizes course completion status.
        Supports both (improved_skill, liked_aspects, would_recommend) and
        (skill_improvement, comments, recommendation) naming styles.
        """
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}

        course = db.session.get(Course, course_id)
        if not course:
            return {'success': False, 'error': 'Course not found'}

        # Support alias parameters
        actual_improved = improved_skill or kwargs.get('skill_improvement') or 'Yes'
        actual_liked = liked_aspects if liked_aspects is not None else kwargs.get('comments', '')
        actual_recommend = would_recommend or kwargs.get('recommendation') or 'Yes'

        # Validate and sanitize rating (1 to 5)
        try:
            clean_rating = max(1, min(5, int(rating)))
        except (ValueError, TypeError):
            clean_rating = 5

        # Validate categorical values
        clean_usefulness = usefulness if usefulness in self.VALID_USEFULNESS else 'Very Useful'
        clean_improved = actual_improved if actual_improved in self.VALID_SKILL_IMPROVED else 'Yes'
        clean_recommend = actual_recommend if actual_recommend in self.VALID_RECOMMEND else 'Yes'

        # Check for existing feedback (prevent duplicate, support edit)
        feedback = CourseFeedback.query.filter_by(user_id=user_id, course_id=course_id).first()
        is_update = feedback is not None

        if not feedback:
            feedback = CourseFeedback(
                user_id=user_id,
                course_id=course_id
            )
            db.session.add(feedback)

        # Update feedback attributes
        feedback.rating = clean_rating
        feedback.usefulness = clean_usefulness
        feedback.improved_skill = clean_improved
        feedback.liked_aspects = (liked_aspects or '').strip()
        feedback.improvement_suggestions = (improvement_suggestions or '').strip()
        feedback.would_recommend = clean_recommend
        feedback.updated_at = datetime.now(timezone.utc)

        # Automatically mark the course completed in ProgressService if not already completed
        progress_service.update_course_progress(
            user_id=user_id,
            course_id=course_id,
            status='Completed',
            progress_percentage=100
        )

        db.session.commit()

        action_msg = "Feedback updated successfully!" if is_update else "Thank you! Your course feedback has been submitted successfully."

        return {
            'success': True,
            'is_update': is_update,
            'feedback': feedback.to_dict(),
            'message': action_msg
        }

    def get_user_feedback(self, user_id: int, course_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves user's submitted feedback for a specific course if present."""
        feedback = CourseFeedback.query.filter_by(user_id=user_id, course_id=course_id).first()
        return feedback.to_dict() if feedback else None

    def get_user_feedbacks(self, user_id: int) -> List[Dict[str, Any]]:
        """Retrieves all course feedbacks submitted by a specific user."""
        feedbacks = CourseFeedback.query.filter_by(user_id=user_id).order_by(CourseFeedback.updated_at.desc(), CourseFeedback.id.desc()).all()
        return [f.to_dict() for f in feedbacks]

    def get_all_feedbacks_for_admin(
        self,
        limit: int = 100,
        course_id: Optional[int] = None,
        min_rating: Optional[int] = None,
        usefulness: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all user feedbacks with metadata for the Admin Dashboard,
        supporting filtering by course, minimum rating, usefulness category, and search keyword.
        """
        query = CourseFeedback.query.join(User).join(Course)

        if course_id:
            query = query.filter(CourseFeedback.course_id == course_id)

        if min_rating:
            query = query.filter(CourseFeedback.rating >= int(min_rating))

        if usefulness and usefulness != 'all':
            query = query.filter(CourseFeedback.usefulness == usefulness)

        if search_query:
            term = f"%{search_query.strip()}%"
            query = query.filter(
                (User.full_name.ilike(term)) |
                (User.email.ilike(term)) |
                (Course.title.ilike(term)) |
                (Course.skill.ilike(term)) |
                (CourseFeedback.liked_aspects.ilike(term)) |
                (CourseFeedback.improvement_suggestions.ilike(term))
            )

        feedbacks = query.order_by(CourseFeedback.created_at.desc()).limit(limit).all()
        return [f.to_dict() for f in feedbacks]

    def get_feedback_analytics(self) -> Dict[str, Any]:
        """
        Aggregates system-wide course feedback metrics for the Admin Dashboard:
        - Total reviews count
        - Average rating across all courses
        - Rating breakdown (1-5 stars)
        - Usefulness distribution
        - Skill improvement rates
        - Course recommendation percentage
        """
        all_feedbacks = CourseFeedback.query.all()
        total_count = len(all_feedbacks)

        if total_count == 0:
            return {
                'total_reviews': 0,
                'average_rating': 5.0,
                'recommendation_rate': 100,
                'skill_improvement_rate': 100,
                'rating_counts': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                'usefulness_counts': {'Very Useful': 0, 'Useful': 0, 'Partially Useful': 0, 'Not Useful': 0},
                'skill_improved_counts': {'Yes': 0, 'Partially': 0, 'No': 0},
                'recommend_counts': {'Yes': 0, 'No': 0}
            }

        total_rating_sum = sum(f.rating for f in all_feedbacks)
        avg_rating = round(total_rating_sum / total_count, 1)

        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        usefulness_counts = {'Very Useful': 0, 'Useful': 0, 'Partially Useful': 0, 'Not Useful': 0}
        skill_improved_counts = {'Yes': 0, 'Partially': 0, 'No': 0}
        recommend_counts = {'Yes': 0, 'No': 0}

        for f in all_feedbacks:
            rating_counts[f.rating] = rating_counts.get(f.rating, 0) + 1
            usefulness_counts[f.usefulness] = usefulness_counts.get(f.usefulness, 0) + 1
            skill_improved_counts[f.improved_skill] = skill_improved_counts.get(f.improved_skill, 0) + 1
            recommend_counts[f.would_recommend] = recommend_counts.get(f.would_recommend, 0) + 1

        recommend_pct = int(round((recommend_counts.get('Yes', 0) / total_count) * 100))
        skill_improved_pct = int(round(((skill_improved_counts.get('Yes', 0) + 0.5 * skill_improved_counts.get('Partially', 0)) / total_count) * 100))

        return {
            'total_reviews': total_count,
            'average_rating': avg_rating,
            'recommendation_rate': recommend_pct,
            'skill_improvement_rate': skill_improved_pct,
            'rating_counts': rating_counts,
            'usefulness_counts': usefulness_counts,
            'skill_improved_counts': skill_improved_counts,
            'recommend_counts': recommend_counts
        }


# Singleton service instance
feedback_service = FeedbackService()
