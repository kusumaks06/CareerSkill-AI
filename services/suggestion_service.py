from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import db, User, Suggestion, LearningActivity


class SuggestionService:
    """
    Service handling user feedback, platform enhancement suggestions,
    moderation workflows, and administrative review analytics.
    """

    CATEGORIES = [
        'Missing Career',
        'Missing Skill',
        'Missing Course',
        'Incorrect Recommendation',
        'Incorrect Market Information',
        'Roadmap Suggestion',
        'General Suggestion'
    ]

    STATUSES = [
        'Submitted',
        'Under Review',
        'Resolved',
        'Rejected'
    ]

    def submit_suggestion(
        self,
        user_id: int,
        category: str,
        title: str,
        description: str,
        career: Optional[str] = None,
        skill: Optional[str] = None,
        course: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submits a new user suggestion or improvement report.
        Initial status is always 'Submitted'.
        """
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}

        clean_title = (title or '').strip()
        clean_desc = (description or '').strip()

        if not clean_title:
            return {'success': False, 'error': 'Suggestion title is required'}
        if not clean_desc:
            return {'success': False, 'error': 'Suggestion description is required'}

        clean_category = category.strip() if category and category.strip() in self.CATEGORIES else 'General Suggestion'
        clean_career = (career or '').strip() or None
        clean_skill = (skill or '').strip() or None
        clean_course = (course or '').strip() or None

        suggestion = Suggestion(
            user_id=user_id,
            category=clean_category,
            title=clean_title,
            description=clean_desc,
            career=clean_career,
            skill=clean_skill,
            course=clean_course,
            status='Submitted'
        )
        db.session.add(suggestion)

        # Log learning activity
        activity = LearningActivity(
            user_id=user_id,
            activity_type='Suggestion',
            title=f"Submitted {clean_category}: '{clean_title}'",
            skill=clean_skill or clean_career or 'Platform Feedback',
            notes=clean_desc[:250]
        )
        db.session.add(activity)

        db.session.commit()

        return {
            'success': True,
            'suggestion': suggestion.to_dict(),
            'message': 'Thank you! Your suggestion has been submitted successfully for review.'
        }

    def get_user_suggestions(self, user_id: int) -> List[Dict[str, Any]]:
        """Retrieves all suggestions submitted by a specific user."""
        suggestions = Suggestion.query.filter_by(user_id=user_id).order_by(
            Suggestion.created_at.desc(),
            Suggestion.id.desc()
        ).all()
        return [s.to_dict() for s in suggestions]

    def get_suggestion_by_id(self, suggestion_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a single suggestion, optionally verifying user ownership."""
        query = Suggestion.query.filter_by(id=suggestion_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        suggestion = query.first()
        return suggestion.to_dict() if suggestion else None

    def update_user_suggestion(
        self,
        suggestion_id: int,
        user_id: int,
        title: str,
        description: str,
        category: Optional[str] = None,
        career: Optional[str] = None,
        skill: Optional[str] = None,
        course: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Allows users to update their suggestion ONLY when the status is 'Submitted'.
        Prevents modifications once admin review has commenced or status resolved.
        """
        suggestion = Suggestion.query.filter_by(id=suggestion_id, user_id=user_id).first()
        if not suggestion:
            return {'success': False, 'error': 'Suggestion not found or access denied'}

        if suggestion.status != 'Submitted':
            return {
                'success': False,
                'error': f"Suggestions with status '{suggestion.status}' cannot be modified."
            }

        clean_title = (title or '').strip()
        clean_desc = (description or '').strip()

        if not clean_title:
            return {'success': False, 'error': 'Title cannot be empty'}
        if not clean_desc:
            return {'success': False, 'error': 'Description cannot be empty'}

        if category and category.strip() in self.CATEGORIES:
            suggestion.category = category.strip()

        suggestion.title = clean_title
        suggestion.description = clean_desc
        suggestion.career = (career or '').strip() or None
        suggestion.skill = (skill or '').strip() or None
        suggestion.course = (course or '').strip() or None
        suggestion.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        return {
            'success': True,
            'suggestion': suggestion.to_dict(),
            'message': 'Suggestion updated successfully!'
        }

    def delete_user_suggestion(self, suggestion_id: int, user_id: int) -> Dict[str, Any]:
        """
        Allows users to delete their suggestion ONLY when the status is 'Submitted'.
        """
        suggestion = Suggestion.query.filter_by(id=suggestion_id, user_id=user_id).first()
        if not suggestion:
            return {'success': False, 'error': 'Suggestion not found or access denied'}

        if suggestion.status != 'Submitted':
            return {
                'success': False,
                'error': f"Suggestions with status '{suggestion.status}' cannot be deleted."
            }

        db.session.delete(suggestion)
        db.session.commit()

        return {
            'success': True,
            'message': 'Suggestion deleted successfully.'
        }

    def get_all_suggestions_for_admin(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Retrieves suggestions with user metadata for administrative oversight,
        supporting filtering by status, category, and keyword search.
        """
        query = Suggestion.query.join(User)

        if status and status != 'all':
            query = query.filter(Suggestion.status == status)

        if category and category != 'all':
            query = query.filter(Suggestion.category == category)

        if search_query:
            term = f"%{search_query.strip()}%"
            query = query.filter(
                (User.full_name.ilike(term)) |
                (User.email.ilike(term)) |
                (Suggestion.title.ilike(term)) |
                (Suggestion.description.ilike(term)) |
                (Suggestion.career.ilike(term)) |
                (Suggestion.skill.ilike(term)) |
                (Suggestion.course.ilike(term)) |
                (Suggestion.admin_response.ilike(term))
            )

        suggestions = query.order_by(
            Suggestion.created_at.desc(),
            Suggestion.id.desc()
        ).limit(limit).all()

        return [s.to_dict() for s in suggestions]

    def admin_update_suggestion(
        self,
        suggestion_id: int,
        status: str,
        admin_response: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Admin action to update a suggestion's review status and post administrative responses.
        """
        suggestion = db.session.get(Suggestion, suggestion_id)
        if not suggestion:
            return {'success': False, 'error': 'Suggestion not found'}

        if status not in self.STATUSES:
            return {'success': False, 'error': f"Invalid status '{status}'. Valid options: {self.STATUSES}"}

        suggestion.status = status
        if admin_response is not None:
            suggestion.admin_response = admin_response.strip()

        suggestion.updated_at = datetime.now(timezone.utc)

        if status in ['Resolved', 'Rejected']:
            if not suggestion.resolved_at:
                suggestion.resolved_at = datetime.now(timezone.utc)
        else:
            suggestion.resolved_at = None

        db.session.commit()

        return {
            'success': True,
            'suggestion': suggestion.to_dict(),
            'message': f"Suggestion marked as '{status}'."
        }

    def get_suggestion_analytics(self) -> Dict[str, Any]:
        """
        Computes aggregate metrics, status distribution, and top requested project enhancements.
        """
        all_suggestions = Suggestion.query.all()
        total = len(all_suggestions)

        status_counts = {
            'Submitted': 0,
            'Under Review': 0,
            'Resolved': 0,
            'Rejected': 0
        }

        category_counts = {cat: 0 for cat in self.CATEGORIES}
        careers_list = []
        skills_list = []
        courses_list = []

        for s in all_suggestions:
            if s.status in status_counts:
                status_counts[s.status] += 1
            if s.category in category_counts:
                category_counts[s.category] += 1
            if s.career:
                careers_list.append(s.career.strip())
            if s.skill:
                skills_list.append(s.skill.strip())
            if s.course:
                courses_list.append(s.course.strip())

        top_careers = [{'name': name, 'count': count} for name, count in Counter(careers_list).most_common(5)]
        top_skills = [{'name': name, 'count': count} for name, count in Counter(skills_list).most_common(5)]
        top_courses = [{'name': name, 'count': count} for name, count in Counter(courses_list).most_common(5)]

        resolved_count = status_counts.get('Resolved', 0)
        resolution_rate = round((resolved_count / total * 100), 1) if total > 0 else 0.0

        return {
            'total_suggestions': total,
            'status_counts': status_counts,
            'new_count': status_counts.get('Submitted', 0),
            'under_review_count': status_counts.get('Under Review', 0),
            'resolved_count': resolved_count,
            'rejected_count': status_counts.get('Rejected', 0),
            'resolution_rate': resolution_rate,
            'category_counts': category_counts,
            'top_requested_careers': top_careers,
            'top_requested_skills': top_skills,
            'top_reported_courses': top_courses
        }


# Singleton service instance
suggestion_service = SuggestionService()
