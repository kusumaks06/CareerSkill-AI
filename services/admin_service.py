import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from models import (
    db,
    User,
    UserProfile,
    UserSkill,
    TargetCareer,
    SkillGapAnalysis,
    SkillGapItem,
    Course,
    CourseProgress,
    UserCourseRecommendation,
    CourseFeedback,
    UserRoadmap,
    RoadmapMilestone,
    AssessmentQuestion,
    AssessmentAttempt,
    LearningActivity,
    Suggestion,
    CustomCareer,
    SkillDefinition,
    MarketRequirement,
    AdminActivityLog
)


class AdminService:
    """
    Core administrative service powering enterprise system oversight,
    curriculum governance, user management, and real database analytics.
    """

    def __init__(self):
        self.careers_json_path = Path(__file__).resolve().parent.parent / 'data' / 'careers.json'
        self.market_json_path = Path(__file__).resolve().parent.parent / 'data' / 'market_requirements.json'

    # ---------------------------------------------------------
    # Admin Activity Logging Helper
    # ---------------------------------------------------------
    def log_admin_action(
        self,
        admin_id: Optional[int],
        admin_name: str,
        action: str,
        target_type: Optional[str] = None,
        target_name: Optional[str] = None,
        details: Optional[str] = None
    ) -> None:
        """Safely records administrative governance actions to the audit log."""
        try:
            log_entry = AdminActivityLog(
                admin_id=admin_id,
                admin_name=admin_name or 'Administrator',
                action=action,
                target_type=target_type,
                target_name=target_name,
                details=details
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            db.session.rollback()

    def get_admin_activity_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves administrative activity logs sorted by recent event."""
        logs = AdminActivityLog.query.order_by(AdminActivityLog.created_at.desc(), AdminActivityLog.id.desc()).limit(limit).all()
        return [l.to_dict() for l in logs]

    # ---------------------------------------------------------
    # Overview Dashboard Metrics
    # ---------------------------------------------------------
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Calculates core platform summary KPIs, missing skills, and recent activity streams."""
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        career_searches = TargetCareer.query.count()
        gap_analyses = SkillGapAnalysis.query.count()
        total_courses = Course.query.count()
        total_job_roles = len(self.get_careers_list())
        course_completions = CourseProgress.query.filter_by(status='Completed').count()
        assessment_attempts = AssessmentAttempt.query.count()

        # Average readiness
        all_analyses = SkillGapAnalysis.query.all()
        avg_readiness = 0.0
        if all_analyses:
            avg_readiness = round(sum(a.readiness_score for a in all_analyses) / len(all_analyses), 1)

        feedback_count = CourseFeedback.query.count()
        feedbacks = CourseFeedback.query.all()
        avg_rating = round(sum(f.rating for f in feedbacks) / len(feedbacks), 1) if feedbacks else 0.0
        satisfaction_pct = round((sum(1 for f in feedbacks if f.rating >= 4) / len(feedbacks) * 100), 1) if feedbacks else 100.0

        suggestions_count = Suggestion.query.count()
        suggestions_pending = Suggestion.query.filter_by(status='Submitted').count()

        # Popular careers chart data
        target_careers = TargetCareer.query.all()
        career_counts = Counter(tc.career_name for tc in target_careers if tc.career_name)
        popular_careers = [{'career': name, 'count': count} for name, count in career_counts.most_common(6)]

        # Most missing skills aggregation
        gap_items = SkillGapItem.query.all()
        gap_status_counts = Counter(item.status for item in gap_items if item.status)
        missing_skills_counter = Counter(item.skill_name for item in gap_items if item.status == 'Missing')
        most_missing_skills = [{'skill': name, 'count': count} for name, count in missing_skills_counter.most_common(5)]

        # Most popular courses aggregation
        progress_items = CourseProgress.query.all()
        progress_counts = Counter(p.status for p in progress_items if p.status)
        course_enrollment_counts = Counter(p.course_id for p in progress_items)
        most_popular_courses = []
        for c_id, count in course_enrollment_counts.most_common(5):
            c_obj = db.session.get(Course, c_id)
            if c_obj:
                most_popular_courses.append({
                    'id': c_obj.id,
                    'title': c_obj.title,
                    'provider': c_obj.provider,
                    'skill': c_obj.skill,
                    'enrollments': count
                })

        # Recent activities log (sanitized)
        recent_acts = LearningActivity.query.join(User).order_by(
            LearningActivity.created_at.desc(),
            LearningActivity.id.desc()
        ).limit(10).all()

        activity_stream = []
        for act in recent_acts:
            activity_stream.append({
                'id': act.id,
                'user_id': act.user_id,
                'user_name': act.user.full_name if act.user else 'Learner',
                'user_email': act.user.email if act.user else '',
                'activity_type': act.activity_type,
                'title': act.title,
                'skill': act.skill,
                'date': act.created_at.strftime("%d %b %Y, %H:%M") if act.created_at else None
            })

        admin_activities = self.get_admin_activity_logs(limit=10)

        return {
            'total_users': total_users,
            'active_users': active_users,
            'career_searches': career_searches,
            'skill_gap_analyses': gap_analyses,
            'total_courses': total_courses,
            'total_job_roles': total_job_roles,
            'course_completions': course_completions,
            'assessment_attempts': assessment_attempts,
            'average_readiness': avg_readiness,
            'feedback_count': feedback_count,
            'avg_feedback_rating': avg_rating,
            'satisfaction_pct': satisfaction_pct,
            'suggestions_count': suggestions_count,
            'suggestions_pending': suggestions_pending,
            'popular_careers': popular_careers,
            'gap_status_counts': dict(gap_status_counts),
            'most_missing_skills': most_missing_skills,
            'most_popular_courses': most_popular_courses,
            'progress_counts': dict(progress_counts),
            'recent_activities': activity_stream,
            'admin_activities': admin_activities
        }

    # ---------------------------------------------------------
    # 1. User Management
    # ---------------------------------------------------------
    def get_users_list(
        self,
        search_query: Optional[str] = None,
        career_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Retrieves user accounts with progress and readiness metrics (passwords hidden)."""
        query = User.query

        if search_query:
            term = f"%{search_query.strip()}%"
            query = query.filter((User.full_name.ilike(term)) | (User.email.ilike(term)))

        if status_filter == 'active':
            query = query.filter(User.is_active.is_(True))
        elif status_filter == 'inactive':
            query = query.filter(User.is_active.is_(False))

        users = query.order_by(User.created_at.desc(), User.id.desc()).limit(limit).all()

        results = []
        for u in users:
            target_career_obj = TargetCareer.query.filter_by(user_id=u.id).order_by(TargetCareer.id.desc()).first()
            target_career = target_career_obj.career_name if target_career_obj else 'Not Selected'

            if career_filter and career_filter != 'all' and career_filter.lower() not in target_career.lower():
                continue

            latest_analysis = SkillGapAnalysis.query.filter_by(user_id=u.id).order_by(SkillGapAnalysis.created_at.desc()).first()
            readiness = latest_analysis.readiness_score if latest_analysis else 0.0

            enrolled_courses = CourseProgress.query.filter_by(user_id=u.id).count()
            completed_courses = CourseProgress.query.filter_by(user_id=u.id, status='Completed').count()
            assessments_taken = AssessmentAttempt.query.filter_by(user_id=u.id).count()
            skills_count = UserSkill.query.filter_by(user_id=u.id).count()

            results.append({
                'id': u.id,
                'full_name': u.full_name,
                'email': u.email,
                'is_active': u.is_active,
                'is_admin': u.is_admin,
                'role': u.role,
                'target_career': target_career,
                'readiness_score': round(readiness, 1),
                'skills_count': skills_count,
                'enrolled_courses': enrolled_courses,
                'completed_courses': completed_courses,
                'assessments_taken': assessments_taken,
                'created_at': u.created_at.strftime("%d %b %Y") if u.created_at else None
            })

        return results

    def get_user_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves comprehensive 360-degree user inspection (excluding authentication secrets)."""
        user = db.session.get(User, user_id)
        if not user:
            return None

        # User profile
        profile = UserProfile.query.filter_by(user_id=user.id).first()

        # Target careers
        target_careers = [tc.career_name for tc in TargetCareer.query.filter_by(user_id=user.id).all()]

        # Skills
        user_skills = [{
            'skill_name': s.skill_name,
            'proficiency_level': s.proficiency_level,
            'proficiency_score': s.proficiency_score,
            'category': s.category
        } for s in UserSkill.query.filter_by(user_id=user.id).all()]

        # Skill gap analysis
        latest_gap = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.created_at.desc()).first()
        gap_data = None
        if latest_gap:
            items = SkillGapItem.query.filter_by(analysis_id=latest_gap.id).all()
            gap_data = {
                'target_role': latest_gap.target_role,
                'readiness_score': round(latest_gap.readiness_score, 1),
                'readiness_level': latest_gap.readiness_level,
                'created_at': latest_gap.created_at.strftime("%d %b %Y, %H:%M") if latest_gap.created_at else None,
                'items': [{
                    'skill': item.skill_name,
                    'status': item.status,
                    'user_level': item.user_level,
                    'required_level': item.required_level,
                    'priority': item.priority
                } for item in items]
            }

        # Course progress
        courses = []
        for cp in CourseProgress.query.filter_by(user_id=user.id).all():
            courses.append({
                'id': cp.id,
                'course_id': cp.course_id,
                'title': cp.course.title if cp.course else 'Course',
                'provider': cp.course.provider if cp.course else 'Provider',
                'skill': cp.course.skill if cp.course else 'General',
                'status': cp.status,
                'progress_percentage': round(cp.progress_percentage, 1),
                'hours_completed': round(cp.hours_completed, 1),
                'total_hours': round(cp.total_hours, 1)
            })

        # Assessment attempts
        assessments = []
        for att in AssessmentAttempt.query.filter_by(user_id=user.id).order_by(AssessmentAttempt.created_at.desc()).all():
            assessments.append({
                'id': att.id,
                'skill': att.skill_name,
                'score_percentage': round(att.score, 1),
                'passed': att.score >= 60.0,
                'total_questions': att.total_questions,
                'correct_answers': att.correct_count,
                'date': att.created_at.strftime("%d %b %Y, %H:%M") if att.created_at else None
            })

        # Feedbacks
        feedbacks = [f.to_dict() for f in CourseFeedback.query.filter_by(user_id=user.id).all()]

        # Suggestions
        suggestions = [s.to_dict() for s in Suggestion.query.filter_by(user_id=user.id).all()]

        return {
            'id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'is_active': user.is_active,
            'is_admin': user.is_admin,
            'role': user.role,
            'created_at': user.created_at.strftime("%d %b %Y, %H:%M") if user.created_at else None,
            'profile': profile.to_dict() if profile else {},
            'target_careers': target_careers,
            'skills': user_skills,
            'skill_gap': gap_data,
            'courses': courses,
            'assessments': assessments,
            'feedbacks': feedbacks,
            'suggestions': suggestions
        }

    def toggle_user_status(self, user_id: int, is_active: Optional[bool] = None, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Toggles or sets active/inactive status for a user."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}

        if is_active is None:
            user.is_active = not user.is_active
        else:
            user.is_active = is_active

        db.session.commit()
        status_str = 'activated' if user.is_active else 'deactivated'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=f"User {status_str.title()}",
            target_type='User',
            target_name=user.full_name,
            details=f"Account {user.email} status changed to {'Active' if user.is_active else 'Inactive'}"
        )
        return {
            'success': True,
            'is_active': user.is_active,
            'message': f"User account '{user.full_name}' {status_str} successfully."
        }

    def toggle_user_role(self, user_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Promotes a user to administrator or revokes administrative privileges."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found.'}
        if admin_user_id and user.id == admin_user_id:
            return {'success': False, 'error': 'You cannot revoke your own administrator role.'}

        new_is_admin = not user.is_admin
        user.is_admin = new_is_admin
        user.role = 'admin' if new_is_admin else 'user'
        db.session.commit()

        action_desc = "Promoted to Admin" if new_is_admin else "Demoted to Regular User"
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Updated User Role',
            target_type='User',
            target_name=user.full_name,
            details=f"Changed role for {user.email} to {user.role}"
        )
        return {'success': True, 'is_admin': user.is_admin, 'role': user.role, 'message': f"User '{user.full_name}' {action_desc}."}

    def delete_user(self, user_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes a user account and all associated records safely."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found.'}
        if admin_user_id and user.id == admin_user_id:
            return {'success': False, 'error': 'You cannot delete your own administrator account.'}

        user_name = user.full_name
        user_email = user.email

        db.session.delete(user)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted User',
            target_type='User',
            target_name=user_name,
            details=f"Deleted account {user_email} (ID #{user_id})"
        )
        return {'success': True, 'message': f"User account '{user_name}' ({user_email}) deleted successfully."}

    def create_admin_account(self, full_name: str, email: str, password: str, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Creates a new administrator account directly from the admin panel."""
        clean_name = (full_name or '').strip()
        clean_email = (email or '').strip().lower()
        if not clean_name or not clean_email or not password:
            return {'success': False, 'error': 'Full name, valid email, and password are required.'}

        existing = User.query.filter_by(email=clean_email).first()
        if existing:
            return {'success': False, 'error': f"An account with email '{clean_email}' already exists."}

        new_admin = User(
            full_name=clean_name,
            email=clean_email,
            is_admin=True,
            role='admin',
            is_active=True
        )
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Created Admin Account',
            target_type='User',
            target_name=clean_name,
            details=f"Created administrator account for {clean_email}"
        )
        return {'success': True, 'user_id': new_admin.id, 'message': f"Administrator account '{clean_name}' created successfully."}

    # ---------------------------------------------------------
    # 2. Career Management
    # ---------------------------------------------------------
    def get_careers_list(self, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Combines JSON catalog careers and custom DB careers."""
        careers = []
        seen_titles = set()

        # 1. Custom DB careers
        db_careers = CustomCareer.query.all()
        for c in db_careers:
            seen_titles.add(c.normalized_title)
            careers.append({
                'id': c.id,
                'source': 'Database (Custom)',
                'title': c.title,
                'normalized_title': c.normalized_title,
                'category': c.category,
                'description': c.description,
                'core_skills': c.core_skills,
                'secondary_skills': c.secondary_skills,
                'experience_level': c.experience_level or 'All Experience Levels',
                'salary_range': c.salary_range or '₹6,00,000 - ₹15,00,000 / yr',
                'market_demand': c.market_demand or 'High Demand',
                'priority': c.priority,
                'is_active': c.is_active
            })

        # 2. File catalog careers
        if self.careers_json_path.exists():
            try:
                with open(self.careers_json_path, 'r', encoding='utf-8') as f:
                    file_careers = json.load(f)
                    for fc in file_careers:
                        norm = fc.get('normalized_title', fc.get('title', '').lower())
                        if norm not in seen_titles:
                            careers.append({
                                'id': None,
                                'source': 'System Catalog',
                                'title': fc.get('title', ''),
                                'normalized_title': norm,
                                'category': fc.get('category', 'Technology'),
                                'description': fc.get('description', ''),
                                'core_skills': fc.get('core_skills', []),
                                'secondary_skills': fc.get('secondary_skills', []),
                                'experience_level': fc.get('experience_level', 'All Experience Levels'),
                                'salary_range': fc.get('salary_range', '₹6,00,000 - ₹15,00,000 / yr'),
                                'market_demand': fc.get('market_demand', 'High Demand'),
                                'priority': 1,
                                'is_active': True
                            })
            except Exception:
                pass

        if search_query:
            q = search_query.lower()
            careers = [c for c in careers if q in c['title'].lower() or q in c['category'].lower() or any(q in s.lower() for s in c['core_skills'])]

        return careers

    def save_career(
        self,
        title: str,
        category: str,
        description: str,
        core_skills: Any,
        secondary_skills: Any = None,
        experience_level: str = 'All Experience Levels',
        salary_range: str = '₹6,00,000 - ₹15,00,000 / yr',
        market_demand: str = 'High Demand',
        priority: int = 1,
        career_id: Optional[int] = None,
        admin_user_id: Optional[int] = None,
        admin_name: str = 'Administrator'
    ) -> Dict[str, Any]:
        """Creates or updates a custom career."""
        clean_title = (title or '').strip()
        if not clean_title:
            return {'success': False, 'error': 'Career title is required'}

        norm_title = clean_title.lower()

        if career_id:
            career = db.session.get(CustomCareer, career_id)
            if not career:
                return {'success': False, 'error': 'Career record not found'}
        else:
            existing = CustomCareer.query.filter_by(normalized_title=norm_title).first()
            if existing:
                career = existing
            else:
                career = CustomCareer(title=clean_title, normalized_title=norm_title)
                db.session.add(career)

        career.title = clean_title
        career.normalized_title = norm_title
        career.category = (category or 'Technology').strip()
        career.description = (description or '').strip()
        career.core_skills = core_skills
        career.secondary_skills = secondary_skills or []
        career.experience_level = (experience_level or 'All Experience Levels').strip()
        career.salary_range = (salary_range or '₹6,00,000 - ₹15,00,000 / yr').strip()
        career.market_demand = (market_demand or 'High Demand').strip()
        career.priority = priority
        career.is_active = True

        db.session.commit()
        action_verb = 'Updated Career' if career_id else 'Created Career'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=action_verb,
            target_type='Career',
            target_name=clean_title,
            details=f"{action_verb} '{clean_title}' in category {career.category}"
        )
        return {'success': True, 'career': career.to_dict(), 'message': 'Career saved successfully!'}

    def delete_career(self, career_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes a custom career record."""
        career = db.session.get(CustomCareer, career_id)
        if not career:
            return {'success': False, 'error': 'Custom career not found'}

        c_title = career.title
        db.session.delete(career)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted Career',
            target_type='Career',
            target_name=c_title,
            details=f"Deleted custom career '{c_title}' (ID #{career_id})"
        )
        return {'success': True, 'message': 'Custom career deleted successfully.'}

    # ---------------------------------------------------------
    # 3. Skill Management
    # ---------------------------------------------------------
    def get_skills_list(self, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all defined skills across database and courses."""
        skills = []
        seen = set()

        for s in SkillDefinition.query.all():
            seen.add(s.name.lower())
            skills.append(s.to_dict())

        # Extract unique skills from Course catalog if not in SkillDefinition
        for c in Course.query.all():
            s_name = c.skill.strip()
            if s_name.lower() not in seen:
                seen.add(s_name.lower())
                skills.append({
                    'id': None,
                    'name': s_name,
                    'category': c.category or 'Technical',
                    'description': f"Skill covered in courses including '{c.title}'",
                    'topics': c.get_topics() if hasattr(c, 'get_topics') else [],
                    'difficulty': c.difficulty or 'Moderate',
                    'demand_status': 'In-Demand',
                    'is_active': True,
                    'created_at': None
                })

        if search_query:
            q = search_query.lower()
            skills = [s for s in skills if q in s['name'].lower() or q in s['category'].lower() or q in s.get('demand_status', '').lower()]

        return skills

    def save_skill(
        self,
        name: str,
        category: str,
        description: str,
        topics: Any,
        difficulty: str = 'Moderate',
        demand_status: str = 'In-Demand',
        skill_id: Optional[int] = None,
        admin_user_id: Optional[int] = None,
        admin_name: str = 'Administrator'
    ) -> Dict[str, Any]:
        """Creates or updates a skill definition."""
        clean_name = (name or '').strip()
        if not clean_name:
            return {'success': False, 'error': 'Skill name is required'}

        if skill_id:
            skill = db.session.get(SkillDefinition, skill_id)
            if not skill:
                return {'success': False, 'error': 'Skill record not found'}
        else:
            existing = SkillDefinition.query.filter_by(name=clean_name).first()
            if existing:
                skill = existing
            else:
                skill = SkillDefinition(name=clean_name)
                db.session.add(skill)

        skill.name = clean_name
        skill.category = (category or 'Technical').strip()
        skill.description = (description or '').strip()
        skill.topics = topics
        skill.difficulty = (difficulty or 'Moderate').strip()
        skill.demand_status = (demand_status or 'In-Demand').strip()
        skill.is_active = True

        db.session.commit()
        action_verb = 'Updated Skill' if skill_id else 'Created Skill'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=action_verb,
            target_type='Skill',
            target_name=clean_name,
            details=f"{action_verb} '{clean_name}' (Status: {skill.demand_status})"
        )
        return {'success': True, 'skill': skill.to_dict(), 'message': 'Skill saved successfully!'}

    def delete_skill(self, skill_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes a skill definition."""
        skill = db.session.get(SkillDefinition, skill_id)
        if not skill:
            return {'success': False, 'error': 'Skill not found'}

        s_name = skill.name
        db.session.delete(skill)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted Skill',
            target_type='Skill',
            target_name=s_name,
            details=f"Deleted skill definition '{s_name}' (ID #{skill_id})"
        )
        return {'success': True, 'message': 'Skill deleted successfully.'}

    # ---------------------------------------------------------
    # 4. Market Requirements
    # ---------------------------------------------------------
    def get_market_requirements(
        self,
        career_filter: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves labor market requirement benchmarks."""
        requirements = []

        # DB requirements
        db_reqs = MarketRequirement.query.all()
        for r in db_reqs:
            requirements.append(r.to_dict())

        # If DB is empty, pull from JSON catalog
        if not db_reqs and self.market_json_path.exists():
            try:
                with open(self.market_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for role, skills in data.items():
                        for item in skills:
                            requirements.append({
                                'id': None,
                                'career_title': role,
                                'skill_name': item.get('skill', ''),
                                'required_level': item.get('required_level', 'Intermediate'),
                                'importance': item.get('importance', 'Important'),
                                'experience_level': item.get('experience_level', 'Entry to Mid-Level'),
                                'salary_range': item.get('salary_range', 'Industry Standard'),
                                'market_demand': item.get('market_demand', 'High Demand'),
                                'topics': item.get('topics', []),
                                'estimated_hours': float(item.get('estimated_hours', 20.0)),
                                'difficulty': item.get('difficulty', 'Moderate'),
                                'source_reference': 'System Benchmark (2026)',
                                'is_verified': True,
                                'data_type': 'System Benchmark',
                                'updated_at': None
                            })
            except Exception:
                pass

        if career_filter and career_filter != 'all':
            requirements = [r for r in requirements if career_filter.lower() in r['career_title'].lower()]

        if search_query:
            q = search_query.lower()
            requirements = [r for r in requirements if q in r['career_title'].lower() or q in r['skill_name'].lower()]

        return requirements

    def save_market_requirement(
        self,
        career_title: str,
        skill_name: str,
        required_level: str = 'Intermediate',
        importance: str = 'Important',
        experience_level: str = 'Entry to Mid-Level',
        salary_range: str = 'Industry Benchmark',
        market_demand: str = 'High Demand',
        topics: Any = None,
        estimated_hours: float = 20.0,
        difficulty: str = 'Moderate',
        source_reference: str = 'Industry Benchmark',
        is_verified: bool = True,
        req_id: Optional[int] = None,
        admin_user_id: Optional[int] = None,
        admin_name: str = 'Administrator'
    ) -> Dict[str, Any]:
        """Creates or updates a labor market benchmark record."""
        clean_career = (career_title or '').strip()
        clean_skill = (skill_name or '').strip()

        if not clean_career or not clean_skill:
            return {'success': False, 'error': 'Target career and skill name are required'}

        if req_id:
            req = db.session.get(MarketRequirement, req_id)
            if not req:
                return {'success': False, 'error': 'Market requirement not found'}
        else:
            req = MarketRequirement(career_title=clean_career, skill_name=clean_skill)
            db.session.add(req)

        req.career_title = clean_career
        req.skill_name = clean_skill
        req.required_level = required_level
        req.importance = importance
        req.experience_level = (experience_level or 'Entry to Mid-Level').strip()
        req.salary_range = (salary_range or 'Industry Benchmark').strip()
        req.market_demand = (market_demand or 'High Demand').strip()
        req.topics = topics or []
        req.estimated_hours = float(estimated_hours or 20.0)
        req.difficulty = difficulty
        req.source_reference = (source_reference or 'Industry Benchmark').strip()
        req.is_verified = bool(is_verified)

        db.session.commit()
        action_verb = 'Updated Benchmark' if req_id else 'Created Benchmark'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=action_verb,
            target_type='MarketRequirement',
            target_name=f"{clean_career} - {clean_skill}",
            details=f"{action_verb} for {clean_career} ({clean_skill})"
        )
        return {'success': True, 'requirement': req.to_dict(), 'message': 'Market requirement saved successfully!'}

    def delete_market_requirement(self, req_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes a market requirement record."""
        req = db.session.get(MarketRequirement, req_id)
        if not req:
            return {'success': False, 'error': 'Market requirement not found'}

        r_name = f"{req.career_title} - {req.skill_name}"
        db.session.delete(req)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted Benchmark',
            target_type='MarketRequirement',
            target_name=r_name,
            details=f"Deleted market benchmark #{req_id} ({r_name})"
        )
        return {'success': True, 'message': 'Market requirement deleted successfully.'}

    # ---------------------------------------------------------
    # 5. Course Management
    # ---------------------------------------------------------
    def get_courses_list(
        self,
        search_query: Optional[str] = None,
        skill_filter: Optional[str] = None,
        provider_filter: Optional[str] = None,
        limit: int = 300
    ) -> List[Dict[str, Any]]:
        """Retrieves courses catalog with completion and rating statistics."""
        query = Course.query

        if search_query:
            term = f"%{search_query.strip()}%"
            query = query.filter((Course.title.ilike(term)) | (Course.description.ilike(term)))

        if skill_filter and skill_filter != 'all':
            query = query.filter(Course.skill.ilike(f"%{skill_filter.strip()}%"))

        if provider_filter and provider_filter != 'all':
            query = query.filter(Course.provider.ilike(f"%{provider_filter.strip()}%"))

        courses = query.order_by(Course.id.asc()).limit(limit).all()

        results = []
        for c in courses:
            enrolled = CourseProgress.query.filter_by(course_id=c.id).count()
            completed = CourseProgress.query.filter_by(course_id=c.id, status='Completed').count()
            feedback_items = CourseFeedback.query.filter_by(course_id=c.id).all()
            avg_rating = round(sum(f.rating for f in feedback_items) / len(feedback_items), 1) if feedback_items else c.rating

            results.append({
                'id': c.id,
                'title': c.title,
                'provider': c.provider,
                'skill': c.skill,
                'category': c.category,
                'level': c.level,
                'duration_hours': c.duration_hours,
                'difficulty': c.difficulty,
                'url': c.url,
                'is_free': c.is_free,
                'is_active': c.is_active,
                'resource_type': c.resource_type,
                'rating': avg_rating,
                'topics': c.get_topics() if hasattr(c, 'get_topics') else [],
                'enrolled_count': enrolled,
                'completed_count': completed,
                'feedback_count': len(feedback_items)
            })

        return results

    def save_course(
        self,
        title: str,
        provider: str,
        skill: str,
        url: str,
        category: str = 'Technical',
        level: str = 'Beginner',
        duration_hours: float = 10.0,
        difficulty: str = 'Moderate',
        is_free: bool = True,
        resource_type: str = 'Course',
        rating: Optional[float] = None,
        description: Optional[str] = None,
        topics: Any = None,
        course_id: Optional[int] = None,
        admin_user_id: Optional[int] = None,
        admin_name: str = 'Administrator'
    ) -> Dict[str, Any]:
        """Creates or updates a course record."""
        clean_title = (title or '').strip()
        clean_provider = (provider or '').strip()
        clean_skill = (skill or '').strip()
        clean_url = (url or '').strip()

        if not clean_title or not clean_provider or not clean_skill or not clean_url:
            return {'success': False, 'error': 'Title, Provider, Skill, and URL are required'}

        if course_id:
            course = db.session.get(Course, course_id)
            if not course:
                return {'success': False, 'error': 'Course not found'}
        else:
            course = Course(title=clean_title, provider=clean_provider, skill=clean_skill, url=clean_url)
            db.session.add(course)

        course.title = clean_title
        course.provider = clean_provider
        course.skill = clean_skill
        course.url = clean_url
        course.category = category or 'Technical'
        course.level = level or 'Beginner'
        course.duration_hours = float(duration_hours or 10.0)
        course.difficulty = difficulty or 'Moderate'
        course.is_free = bool(is_free)
        course.resource_type = resource_type or 'Course'
        course.rating = float(rating) if rating else 4.8
        course.description = (description or '').strip()
        
        if isinstance(topics, str):
            topics_list = [t.strip() for t in topics.split(',') if t.strip()]
        else:
            topics_list = list(topics or [])
        course.set_topics(topics_list)
        course.is_active = True

        db.session.commit()
        action_verb = 'Updated Course' if course_id else 'Created Course'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=action_verb,
            target_type='Course',
            target_name=clean_title,
            details=f"{action_verb} '{clean_title}' by {clean_provider} (Skill: {clean_skill})"
        )
        return {'success': True, 'course': course.to_dict(), 'message': 'Course saved successfully!'}

    def toggle_course_status(self, course_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Activates or deactivates a course."""
        course = db.session.get(Course, course_id)
        if not course:
            return {'success': False, 'error': 'Course not found'}

        course.is_active = not course.is_active
        db.session.commit()
        status_str = 'activated' if course.is_active else 'deactivated'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=f"Course {status_str.title()}",
            target_type='Course',
            target_name=course.title,
            details=f"Course '{course.title}' {status_str}"
        )
        return {'success': True, 'is_active': course.is_active, 'message': f"Course {'activated' if course.is_active else 'deactivated'}."}

    def delete_course(self, course_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes a course record."""
        course = db.session.get(Course, course_id)
        if not course:
            return {'success': False, 'error': 'Course not found'}

        c_title = course.title
        db.session.delete(course)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted Course',
            target_type='Course',
            target_name=c_title,
            details=f"Deleted course '{c_title}' (ID #{course_id})"
        )
        return {'success': True, 'message': 'Course deleted successfully.'}

    # ---------------------------------------------------------
    # 6. Assessment Management
    # ---------------------------------------------------------
    def get_assessments_list(
        self,
        search_query: Optional[str] = None,
        skill_filter: Optional[str] = None,
        difficulty_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves questions with answer statistics."""
        query = AssessmentQuestion.query

        if search_query:
            term = f"%{search_query.strip()}%"
            query = query.filter((AssessmentQuestion.question_text.ilike(term)) | (AssessmentQuestion.topic.ilike(term)))

        if skill_filter and skill_filter != 'all':
            query = query.filter(AssessmentQuestion.skill.ilike(f"%{skill_filter.strip()}%"))

        if difficulty_filter and difficulty_filter != 'all':
            query = query.filter(AssessmentQuestion.difficulty == difficulty_filter)

        questions = query.order_by(AssessmentQuestion.id.asc()).all()
        results = []
        for q in questions:
            d = q.to_dict(include_correct=True)
            d['question'] = q.question_text
            results.append(d)
        return results

    def save_assessment_question(
        self,
        skill: str,
        question: str,
        options: Any,
        correct_answer: str,
        topic: Optional[str] = None,
        difficulty: str = 'Moderate',
        explanation: Optional[str] = None,
        question_id: Optional[int] = None,
        admin_user_id: Optional[int] = None,
        admin_name: str = 'Administrator'
    ) -> Dict[str, Any]:
        """Creates or updates an assessment question."""
        clean_skill = (skill or '').strip()
        clean_q = (question or '').strip()
        clean_correct = (correct_answer or '').strip()

        if not clean_skill or not clean_q or not clean_correct:
            return {'success': False, 'error': 'Skill, Question text, and Correct Answer are required'}

        if question_id:
            aq = db.session.get(AssessmentQuestion, question_id)
            if not aq:
                return {'success': False, 'error': 'Question not found'}
        else:
            aq = AssessmentQuestion(skill=clean_skill, question_text=clean_q, correct_answer=clean_correct)
            db.session.add(aq)

        aq.skill = clean_skill
        aq.question_text = clean_q
        
        if isinstance(options, str):
            options_list = [line.strip() for line in options.splitlines() if line.strip()]
        else:
            options_list = list(options or [])
        aq.set_options(options_list)
        
        aq.correct_answer = clean_correct
        aq.topic = (topic or clean_skill).strip()
        aq.difficulty = difficulty or 'Moderate'
        aq.explanation = (explanation or '').strip()
        aq.is_active = True

        db.session.commit()
        action_verb = 'Updated Question' if question_id else 'Created Question'
        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action=action_verb,
            target_type='Assessment',
            target_name=f"{clean_skill} - {clean_q[:30]}...",
            details=f"{action_verb} for {clean_skill}"
        )
        return {'success': True, 'question': aq.to_dict(include_correct=True), 'message': 'Assessment question saved successfully!'}

    def delete_assessment_question(self, question_id: int, admin_user_id: Optional[int] = None, admin_name: str = 'Administrator') -> Dict[str, Any]:
        """Deletes an assessment question."""
        aq = db.session.get(AssessmentQuestion, question_id)
        if not aq:
            return {'success': False, 'error': 'Question not found'}

        q_text = aq.question_text[:30]
        db.session.delete(aq)
        db.session.commit()

        self.log_admin_action(
            admin_id=admin_user_id,
            admin_name=admin_name,
            action='Deleted Question',
            target_type='Assessment',
            target_name=q_text,
            details=f"Deleted question ID #{question_id}"
        )
        return {'success': True, 'message': 'Question deleted successfully.'}

    def get_assessment_analytics(self) -> Dict[str, Any]:
        """Calculates attempts, average scores, pass rate, and difficulty rankings."""
        total_questions = AssessmentQuestion.query.count()
        attempts = AssessmentAttempt.query.all()
        total_attempts = len(attempts)

        if not attempts:
            return {
                'total_questions': total_questions,
                'total_attempts': 0,
                'avg_score': 0.0,
                'pass_rate': 0.0,
                'passed_count': 0,
                'failed_count': 0,
                'most_difficult_skills': []
            }

        passed_count = sum(1 for a in attempts if (a.score or 0.0) >= 60.0)
        avg_score = round(sum(a.score or 0.0 for a in attempts) / total_attempts, 1)
        pass_rate = round((passed_count / total_attempts) * 100, 1)

        # Skill performance
        skill_scores = {}
        for a in attempts:
            s_name = a.skill_name or 'General'
            if s_name not in skill_scores:
                skill_scores[s_name] = []
            skill_scores[s_name].append(a.score or 0.0)

        difficult_skills = []
        for s_name, scores in skill_scores.items():
            difficult_skills.append({
                'skill': s_name,
                'attempts': len(scores),
                'avg_score': round(sum(scores) / len(scores), 1)
            })

        difficult_skills.sort(key=lambda x: x['avg_score'])

        return {
            'total_questions': total_questions,
            'total_attempts': total_attempts,
            'avg_score': avg_score,
            'pass_rate': pass_rate,
            'passed_count': passed_count,
            'failed_count': total_attempts - passed_count,
            'most_difficult_skills': difficult_skills[:5]
        }

    # ---------------------------------------------------------
    # 7. Roadmap Usage Analytics
    # ---------------------------------------------------------
    def get_roadmap_analytics(self) -> Dict[str, Any]:
        """Calculates roadmap adoption, target career frequency, and completion rates."""
        roadmaps = UserRoadmap.query.all()
        total_roadmaps = len(roadmaps)

        if not roadmaps:
            return {
                'total_roadmaps': 0,
                'avg_progress': 0.0,
                'top_careers': [],
                'top_skills': [],
                'completed_milestones_count': 0,
                'incomplete_milestones_count': 0
            }

        avg_progress = round(sum((r.completion_percentage or 0) for r in roadmaps) / total_roadmaps, 1)
        career_counts = Counter(r.target_role for r in roadmaps if r.target_role)

        milestones = RoadmapMilestone.query.all()
        completed_m = sum(1 for m in milestones if m.is_completed)
        incomplete_m = len(milestones) - completed_m

        milestone_skills = Counter(m.skill for m in milestones if m.skill)

        return {
            'total_roadmaps': total_roadmaps,
            'avg_progress': avg_progress,
            'top_careers': [{'career': c, 'count': n} for c, n in career_counts.most_common(5)],
            'top_skills': [{'skill': s, 'count': n} for s, n in milestone_skills.most_common(5)],
            'completed_milestones_count': completed_m,
            'incomplete_milestones_count': incomplete_m
        }

    # ---------------------------------------------------------
    # 8. Full Platform Analytics (Real Database Aggregation)
    # ---------------------------------------------------------
    def get_full_analytics(self) -> Dict[str, Any]:
        """
        Computes in-depth analytics across Careers, Skill Gaps, Courses, and User Growth.
        Uses actual database data without fabricating statistics.
        """
        # 1. Career Analytics
        target_careers = TargetCareer.query.all()
        has_career_data = len(target_careers) > 0
        career_popularity = []
        if has_career_data:
            c_counts = Counter(tc.career_name for tc in target_careers if tc.career_name)
            for c_name, count in c_counts.most_common(6):
                # Calculate average readiness for this career
                analyses = SkillGapAnalysis.query.filter(SkillGapAnalysis.target_role.ilike(f"%{c_name}%")).all()
                c_avg_readiness = round(sum(a.readiness_score for a in analyses) / len(analyses), 1) if analyses else 0.0
                career_popularity.append({
                    'career': c_name,
                    'users_count': count,
                    'avg_readiness': c_avg_readiness
                })

        # 2. Skill Gap Analytics (Missing, Partial, Strong)
        all_gap_items = SkillGapItem.query.all()
        has_gap_data = len(all_gap_items) > 0

        missing_skills_ranking = []
        partial_skills_ranking = []
        strong_skills_ranking = []

        if has_gap_data:
            total_analyses = max(1, SkillGapAnalysis.query.count())
            missing_counts = Counter(item.skill_name for item in all_gap_items if item.status == 'Missing')
            partial_counts = Counter(item.skill_name for item in all_gap_items if item.status == 'Partial')
            strong_counts = Counter(item.skill_name for item in all_gap_items if item.status == 'Strong')

            for s_name, count in missing_counts.most_common(5):
                pct = round((count / total_analyses) * 100, 1)
                missing_skills_ranking.append({'skill': s_name, 'count': count, 'percentage': pct})

            for s_name, count in partial_counts.most_common(5):
                pct = round((count / total_analyses) * 100, 1)
                partial_skills_ranking.append({'skill': s_name, 'count': count, 'percentage': pct})

            for s_name, count in strong_counts.most_common(5):
                pct = round((count / total_analyses) * 100, 1)
                strong_skills_ranking.append({'skill': s_name, 'count': count, 'percentage': pct})

        # 3. Course Analytics
        course_progresses = CourseProgress.query.all()
        has_course_data = len(course_progresses) > 0
        most_completed_courses = []
        highest_rated_courses = []

        if has_course_data:
            comp_counts = Counter(cp.course_id for cp in course_progresses if cp.status == 'Completed')
            for c_id, count in comp_counts.most_common(5):
                c_obj = db.session.get(Course, c_id)
                if c_obj:
                    most_completed_courses.append({
                        'title': c_obj.title,
                        'provider': c_obj.provider,
                        'completions': count
                    })

        # Highest rated courses
        all_courses = Course.query.filter(Course.rating.isnot(None)).order_by(Course.rating.desc()).limit(5).all()
        for c in all_courses:
            highest_rated_courses.append({
                'title': c.title,
                'provider': c.provider,
                'rating': c.rating,
                'skill': c.skill
            })

        # Course completion overall rate
        total_enrolled = len(course_progresses)
        total_completed = sum(1 for cp in course_progresses if cp.status == 'Completed')
        course_completion_rate = round((total_completed / total_enrolled * 100), 1) if total_enrolled > 0 else 0.0

        return {
            'has_career_data': has_career_data,
            'career_popularity': career_popularity,
            'has_gap_data': has_gap_data,
            'missing_skills': missing_skills_ranking,
            'partial_skills': partial_skills_ranking,
            'strong_skills': strong_skills_ranking,
            'has_course_data': has_course_data,
            'most_completed_courses': most_completed_courses,
            'highest_rated_courses': highest_rated_courses,
            'course_completion_rate': course_completion_rate,
            'total_course_enrollments': total_enrolled,
            'total_course_completions': total_completed
        }


# Singleton instance
admin_service = AdminService()
