import json
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple

from models import (
    db, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    SkillGapAnalysis, 
    SkillGapItem,
    Course, 
    UserCourseRecommendation,
    UserRoadmap, 
    RoadmapMilestone,
    AssessmentAttempt, 
    CourseProgress, 
    LearningActivity, 
    SkillProgressHistory,
    PROFICIENCY_SCORE_MAP
)
from services.skill_normalizer import normalize_skill, skills_match
from services.skill_gap_service import skill_gap_service
from services.roadmap_service import roadmap_service
from services.recommendation_service import recommendation_service


class ProgressService:
    """
    Complete Learning Progress Tracking & Readiness Synchronization Service.
    Tracks course progression, roadmap completions, actual learning hours,
    skill evolution over time, and dynamic career readiness calculations.
    """

    def get_or_create_course_progress(self, user_id: int, course_id: int) -> CourseProgress:
        """Retrieves or creates a CourseProgress record for a user and course."""
        cp = CourseProgress.query.filter_by(user_id=user_id, course_id=course_id).first()
        if not cp:
            course = db.session.get(Course, course_id)
            total_h = course.duration_hours if course else 10.0
            cp = CourseProgress(
                user_id=user_id,
                course_id=course_id,
                status='Not Started',
                progress_percentage=0,
                hours_completed=0.0,
                total_hours=total_h
            )
            db.session.add(cp)
            db.session.commit()
        return cp

    def update_course_progress(
        self,
        user_id: int,
        course_id: int,
        status: Optional[str] = None,
        progress_percentage: Optional[int] = None,
        hours_completed: Optional[float] = None,
        log_activity: bool = True
    ) -> Dict[str, Any]:
        """
        Updates course progress percentage and hours.
        Logs learning activity and triggers cascading skill/readiness updates on completion.
        """
        cp = self.get_or_create_course_progress(user_id, course_id)
        course = db.session.get(Course, course_id)
        user = db.session.get(User, user_id)
        
        prev_pct = cp.progress_percentage
        prev_hours = cp.hours_completed

        # Update progress fields
        new_pct = progress_percentage if progress_percentage is not None else prev_pct
        if status == 'Completed' and progress_percentage is None:
            new_pct = 100
        elif status == 'Not Started' and progress_percentage is None:
            new_pct = 0

        cp.update_progress(pct=new_pct, hours=hours_completed, status=status)

        # Synchronize with UserCourseRecommendation record
        rec = UserCourseRecommendation.query.filter_by(user_id=user_id, course_id=course_id).first()
        if rec:
            rec.status = cp.status
            if cp.status == 'In Progress' and not rec.started_at:
                rec.started_at = datetime.now(timezone.utc)
            elif cp.status == 'Completed':
                rec.completed_at = datetime.now(timezone.utc)

        # Log Learning Activity if progress or hours advanced
        delta_pct = max(0, cp.progress_percentage - prev_pct)
        delta_hours = max(0.0, round(cp.hours_completed - prev_hours, 1))

        if log_activity and (delta_pct > 0 or delta_hours > 0 or cp.status == 'Completed'):
            activity_title = f"{course.title if course else 'Course'} ({cp.status})"
            skill_name = course.skill if course else 'General'
            
            act = LearningActivity(
                user_id=user_id,
                activity_type='Course',
                title=activity_title,
                skill=skill_name,
                hours=delta_hours if delta_hours > 0 else (course.duration_hours if course and cp.status == 'Completed' and prev_pct == 0 else 1.0),
                progress_delta=float(delta_pct),
                notes=f"Progress reached {cp.progress_percentage}% ({cp.hours_completed}/{cp.total_hours} hrs)"
            )
            db.session.add(act)

        # If completed, boost skill proficiency in UserSkill & record skill progress history
        if cp.status == 'Completed' and course and user:
            self._handle_course_completion_skill_boost(user, course)
            self._sync_roadmap_on_course_completion(user.id, course)

        db.session.commit()

        # Recalculate Career Readiness
        readiness_info = self.calculate_career_readiness(user=user)

        return {
            'success': True,
            'progress': cp.to_dict(),
            'readiness': readiness_info
        }

    def _sync_roadmap_on_course_completion(self, user_id: int, course: Course):
        """Advances and synchronizes Roadmap milestones matching the completed course skill."""
        try:
            roadmap = UserRoadmap.query.filter_by(user_id=user_id).order_by(UserRoadmap.id.desc()).first()
            if not roadmap or not roadmap.milestones:
                return

            for milestone in roadmap.milestones:
                if skills_match(milestone.skill, course.skill):
                    tasks = milestone.get_tasks()
                    if tasks:
                        # Mark unfinished tasks matching learning or course completion as done
                        for t in tasks:
                            t['completed'] = True
                        milestone.set_tasks(tasks)
                    milestone.is_completed = True
                    milestone.completed_at = datetime.now(timezone.utc)

            roadmap.calculate_progress()
        except Exception as e:
            print(f"[-] Roadmap synchronization warning on course completion: {e}")

    def _handle_course_completion_skill_boost(self, user: User, course: Course):
        """Boosts skill proficiency score and logs history when a course is completed."""
        user_skills = UserSkill.query.filter_by(user_id=user.id).all()
        target_skill = None
        for us in user_skills:
            if skills_match(us.skill_name, course.skill):
                target_skill = us
                break

        prev_score = target_skill.proficiency_score if target_skill else 0

        # Increment skill score moderately upon course completion (up to 75 / Advanced)
        new_score = min(85, prev_score + 15) if prev_score > 0 else 50
        
        if new_score >= 75:
            new_level = 'Advanced'
        elif new_score >= 50:
            new_level = 'Intermediate'
        else:
            new_level = 'Beginner'

        if target_skill:
            target_skill.proficiency_score = new_score
            target_skill.proficiency_level = new_level
        else:
            target_skill = UserSkill(
                user_id=user.id,
                skill_name=course.skill,
                proficiency_level=new_level,
                proficiency_score=new_score,
                confidence_level=3
            )
            db.session.add(target_skill)

        # Record SkillProgressHistory
        sph = SkillProgressHistory(
            user_id=user.id,
            skill_name=course.skill,
            previous_score=prev_score,
            current_score=new_score,
            target_score=75,
            triggered_by='Course Completion'
        )
        db.session.add(sph)

        # Also add course topics to known topics in SkillGapAnalysis
        topics = course.get_topics()
        if topics:
            saved_analysis = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first()
            if saved_analysis:
                evals = saved_analysis.get_topic_evaluations()
                curr_known = evals.get(course.skill, [])
                evals[course.skill] = list(set(curr_known + topics))
                saved_analysis.set_topic_evaluations(evals)

    def update_roadmap_task_progress(
        self, 
        user_id: int, 
        milestone_id: int, 
        task_id: int, 
        completed: bool, 
        hours_spent: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Updates task completion in a roadmap milestone, logs learning activity,
        and recalculates roadmap progress and career readiness.
        """
        user = db.session.get(User, user_id)
        milestone = db.session.get(RoadmapMilestone, milestone_id)
        if not milestone:
            return {'success': False, 'error': 'Milestone not found'}

        roadmap = milestone.roadmap
        tasks = milestone.get_tasks()
        task_name = f"Task #{task_id}"
        est_hours = 2.0

        for t in tasks:
            if t.get('id') == task_id or t.get('task') == task_id:
                t['completed'] = completed
                task_name = t.get('task', task_name)
                est_hours = float(t.get('estimated_hours', est_hours))
                break

        milestone.set_tasks(tasks)
        
        # Check if all tasks in milestone are completed
        all_done = all(t.get('completed', False) for t in tasks) if tasks else completed
        milestone.is_completed = all_done
        if all_done:
            milestone.completed_at = datetime.now(timezone.utc)

        # Recalculate roadmap overall progress %
        roadmap.calculate_progress()

        # Log learning activity if marked completed
        if completed and user:
            act = LearningActivity(
                user_id=user_id,
                activity_type='Roadmap',
                title=f"{milestone.title}: {task_name}",
                skill=milestone.skill,
                hours=hours_spent if hours_spent is not None else est_hours,
                progress_delta=2.5,
                notes=f"Roadmap progress: {roadmap.completion_percentage}%"
            )
            db.session.add(act)

        db.session.commit()

        # Recalculate Career Readiness
        readiness_info = self.calculate_career_readiness(user=user)

        return {
            'success': True,
            'roadmap_progress': roadmap.completion_percentage,
            'milestone_completed': milestone.is_completed,
            'readiness': readiness_info
        }

    def log_learning_session(
        self, 
        user_id: int, 
        skill: str, 
        title: str, 
        hours: float, 
        notes: Optional[str] = None, 
        progress_delta: float = 0.0
    ) -> Dict[str, Any]:
        """Manually records a study session or project practice activity."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}

        hours = max(0.25, float(hours))
        act = LearningActivity(
            user_id=user_id,
            activity_type='Study Session',
            title=title or f"Independent {skill} Practice",
            skill=skill or 'General',
            hours=hours,
            progress_delta=float(progress_delta),
            notes=notes
        )
        db.session.add(act)
        db.session.commit()

        return {
            'success': True,
            'activity': act.to_dict(),
            'hours_summary': self.get_learning_hours_summary(user_id)
        }

    def get_learning_hours_summary(self, user_id: Optional[int]) -> Dict[str, Any]:
        """
        Computes learning hours breakdown: Today, This Week, This Month, Total,
        and compares against the user's weekly planned schedule.
        """
        if not user_id:
            return {
                'today_hours': 0.0,
                'week_hours': 0.0,
                'month_hours': 0.0,
                'total_hours': 0.0,
                'planned_weekly_hours': 10.0,
                'planned_vs_completed_pct': 0
            }

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)

        activities = LearningActivity.query.filter_by(user_id=user_id).all()

        today_hours = sum(a.hours for a in activities if a.activity_date and a.activity_date.replace(tzinfo=timezone.utc if a.activity_date.tzinfo is None else a.activity_date.tzinfo) >= today_start)
        week_hours = sum(a.hours for a in activities if a.activity_date and a.activity_date.replace(tzinfo=timezone.utc if a.activity_date.tzinfo is None else a.activity_date.tzinfo) >= week_start)
        month_hours = sum(a.hours for a in activities if a.activity_date and a.activity_date.replace(tzinfo=timezone.utc if a.activity_date.tzinfo is None else a.activity_date.tzinfo) >= month_start)
        total_hours = sum(a.hours for a in activities)

        # Fetch planned weekly hours from profile
        user_profile = UserProfile.query.filter_by(user_id=user_id).first()
        planned_weekly = user_profile.learning_hours_per_week if user_profile and user_profile.learning_hours_per_week else 10.0

        planned_pct = min(100, int(round((week_hours / planned_weekly) * 100))) if planned_weekly > 0 else 0

        return {
            'today_hours': round(today_hours, 1),
            'week_hours': round(week_hours, 1),
            'month_hours': round(month_hours, 1),
            'total_hours': round(total_hours, 1),
            'planned_weekly_hours': round(planned_weekly, 1),
            'planned_vs_completed_pct': planned_pct
        }

    def get_skill_growth_matrix(self, user_id: Optional[int], target_role: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Calculates skill evolution over time comparing:
        1. Initial Baseline Score (Before)
        2. Current Verified Score (Current)
        3. Market Target Required Score (Required)
        """
        if not user_id:
            return []

        user = db.session.get(User, user_id)
        if not user:
            return []

        tc = TargetCareer.query.filter_by(user_id=user_id).first()
        target_role = target_role or (tc.career_name if tc else 'Data Analyst')

        # Run skill gap to get target required benchmarks
        analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        gap_items = analysis.get('gap_items', [])

        user_skills = UserSkill.query.filter_by(user_id=user_id).all()
        user_skills_map = {us.skill_name.lower(): us for us in user_skills}

        history_records = SkillProgressHistory.query.filter_by(user_id=user_id).order_by(SkillProgressHistory.id.asc()).all()

        growth_list = []
        for item in gap_items:
            s_name = item['skill_name']
            canonical_name = item['normalized_skill_name']
            
            # Find earliest recorded score or fallback to current
            us = user_skills_map.get(s_name.lower()) or user_skills_map.get(canonical_name.lower())
            
            matching_history = [h for h in history_records if skills_match(h.skill_name, s_name)]
            if matching_history:
                before_score = matching_history[0].previous_score
            elif us:
                before_score = us.proficiency_score
            else:
                before_score = item.get('user_score', 0)

            current_score = us.proficiency_score if us else item.get('user_score', 0)
            required_score = item.get('required_score', 75)

            growth_delta = current_score - before_score
            remaining_gap = max(0, required_score - current_score)

            growth_list.append({
                'skill_name': s_name,
                'category': item.get('category', 'Technical'),
                'before_score': before_score,
                'current_score': current_score,
                'required_score': required_score,
                'growth_delta': growth_delta,
                'remaining_gap': remaining_gap,
                'is_target_met': current_score >= required_score
            })

        return growth_list

    def calculate_career_readiness(self, user: Optional[User], target_role: Optional[str] = None) -> Dict[str, Any]:
        """
        Dynamically recalculates overall Career Readiness score based on:
        - Verified skill proficiency scores vs market required weights
        - Course completion percentage
        - Roadmap milestone completion percentage
        - Assessment validation results
        """
        if not user:
            return {
                'previous_readiness': 45,
                'current_readiness': 50,
                'target_readiness': 90,
                'delta': 0
            }

        tc = TargetCareer.query.filter_by(user_id=user.id).first()
        target_role = target_role or (tc.career_name if tc else 'Data Analyst')

        # 1. Base readiness from SkillGapService
        gap_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        base_readiness = gap_analysis.get('readiness_score', 50)

        # 2. Roadmap progress modifier (up to +15% boost for completed milestones)
        roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
        roadmap_pct = roadmap.completion_percentage if roadmap else 0
        roadmap_boost = (roadmap_pct / 100.0) * 10.0

        # 3. Course completion modifier (up to +10% boost)
        cp_records = CourseProgress.query.filter_by(user_id=user.id).all()
        if cp_records:
            completed_courses = sum(1 for c in cp_records if c.status == 'Completed')
            course_boost = min(10.0, (completed_courses / max(1, len(cp_records))) * 10.0)
        else:
            course_boost = 0.0

        # 4. Assessment validation modifier
        attempts = AssessmentAttempt.query.filter_by(user_id=user.id).all()
        if attempts:
            validated_attempts = sum(1 for a in attempts if a.score >= 70)
            assessment_boost = min(10.0, validated_attempts * 2.5)
        else:
            assessment_boost = 0.0

        # Calculate final readiness
        raw_readiness = base_readiness + roadmap_boost + course_boost + assessment_boost
        current_readiness = min(100, max(0, int(round(raw_readiness))))

        # Retrieve saved prior readiness
        saved_gap = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first()
        previous_readiness = saved_gap.readiness_score if saved_gap else max(0, current_readiness - 12)

        return {
            'previous_readiness': previous_readiness,
            'current_readiness': current_readiness,
            'target_readiness': 90,
            'delta': current_readiness - previous_readiness,
            'disclaimer': "Career readiness score is an estimation based on your verified learning activities and does not guarantee employment."
        }

    def get_overall_progress_summary(self, user_id: Optional[int], target_role: Optional[str] = None) -> Dict[str, Any]:
        """
        Consolidates all 9 Dashboard KPIs:
        1. Overall Learning Progress %
        2. Career Readiness %
        3. Courses Completed
        4. Courses In Progress
        5. Topics Completed
        6. Topics Remaining
        7. Skills Improved
        8. Learning Hours Completed
        9. Learning Hours Remaining
        """
        if not user_id:
            return {
                'overall_progress_pct': 0,
                'career_readiness': 50,
                'previous_readiness': 40,
                'target_readiness': 90,
                'courses_completed': 0,
                'courses_in_progress': 0,
                'courses_not_started': 0,
                'topics_completed': 0,
                'topics_remaining': 0,
                'skills_improved_count': 0,
                'learning_hours_completed': 0.0,
                'learning_hours_remaining': 0.0,
                'hours_summary': self.get_learning_hours_summary(None),
                'skill_growth': []
            }

        user = db.session.get(User, user_id)
        tc = TargetCareer.query.filter_by(user_id=user_id).first()
        target_role = target_role or (tc.career_name if tc else 'Data Analyst')

        # 1. Course Stats
        cp_records = CourseProgress.query.filter_by(user_id=user_id).all()
        courses_completed = sum(1 for c in cp_records if c.status == 'Completed')
        courses_in_progress = sum(1 for c in cp_records if c.status == 'In Progress')
        courses_not_started = sum(1 for c in cp_records if c.status == 'Not Started')

        # 2. Topic Stats from Gap Analysis
        gap_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        gap_items = gap_analysis.get('gap_items', [])
        
        topics_completed = sum(len(item.get('known_topics', [])) for item in gap_items)
        topics_remaining = sum(len(item.get('remaining_topics', [])) for item in gap_items)
        learning_hours_remaining = gap_analysis.get('total_learning_hours', 0.0)

        # 3. Learning Hours Summary
        hours_summary = self.get_learning_hours_summary(user_id)
        learning_hours_completed = hours_summary['total_hours']

        # 4. Skill Growth & Improvements
        skill_growth = self.get_skill_growth_matrix(user_id, target_role=target_role)
        skills_improved_count = sum(1 for s in skill_growth if s['growth_delta'] > 0)

        # 5. Roadmap Progress
        roadmap = UserRoadmap.query.filter_by(user_id=user_id).first()
        roadmap_pct = roadmap.completion_percentage if roadmap else 0

        # 6. Overall Learning Progress % calculation
        course_pct = (courses_completed / max(1, len(cp_records))) * 100 if cp_records else 0
        topic_pct = (topics_completed / max(1, topics_completed + topics_remaining)) * 100 if (topics_completed + topics_remaining) > 0 else 0
        overall_progress_pct = int(round((0.4 * topic_pct) + (0.3 * roadmap_pct) + (0.3 * course_pct)))
        overall_progress_pct = min(100, max(0, overall_progress_pct))

        # 7. Career Readiness
        readiness_info = self.calculate_career_readiness(user, target_role=target_role)

        return {
            'overall_progress_pct': overall_progress_pct,
            'career_readiness': readiness_info['current_readiness'],
            'previous_readiness': readiness_info['previous_readiness'],
            'target_readiness': readiness_info['target_readiness'],
            'courses_completed': courses_completed,
            'courses_in_progress': courses_in_progress,
            'courses_not_started': courses_not_started,
            'topics_completed': topics_completed,
            'topics_remaining': topics_remaining,
            'skills_improved_count': skills_improved_count,
            'learning_hours_completed': learning_hours_completed,
            'learning_hours_remaining': learning_hours_remaining,
            'hours_summary': hours_summary,
            'skill_growth': skill_growth,
            'roadmap_progress_pct': roadmap_pct,
            'disclaimer': readiness_info['disclaimer']
        }

    def get_activity_history(self, user_id: Optional[int], limit: int = 50) -> List[Dict[str, Any]]:
        """Returns chronological list of user's learning activities."""
        if not user_id:
            return []

        activities = LearningActivity.query.filter_by(user_id=user_id).order_by(LearningActivity.id.desc()).limit(limit).all()
        return [a.to_dict() for a in activities]


# Singleton service instance
progress_service = ProgressService()
