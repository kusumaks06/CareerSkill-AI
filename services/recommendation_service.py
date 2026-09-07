import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models import (
    db, 
    Course, 
    UserCourseRecommendation, 
    User, 
    UserProfile, 
    UserSkill, 
    TargetCareer, 
    SkillGapAnalysis, 
    SkillGapItem,
    PROFICIENCY_SCORE_MAP
)
from services.skill_normalizer import normalize_skill, skills_match, find_matching_skill
from services.skill_gap_service import skill_gap_service

COURSES_DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'courses.json'

class RecommendationService:
    """Intelligent, Gap-Driven Course & Resource Recommendation Engine."""

    def __init__(self, data_path=None):
        self.data_path = data_path or COURSES_DATA_FILE
        self._vectorizer = None
        self._course_matrix = None

    def seed_courses_if_empty(self):
        """Seeds initial curated courses from JSON into SQLite if courses table is empty."""
        try:
            count = Course.query.count()
            if count > 0:
                return count

            if not os.path.exists(self.data_path):
                print(f"[-] Warning: Courses data file not found at {self.data_path}")
                return 0

            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                course_list = data.get('courses', [])

            seeded_count = 0
            for item in course_list:
                canonical_skill, _ = normalize_skill(item.get('skill', ''))
                course = Course(
                    title=item.get('title', '').strip(),
                    description=item.get('description', '').strip(),
                    provider=item.get('provider', 'Online Platform').strip(),
                    skill=canonical_skill or item.get('skill', '').strip(),
                    category=item.get('category', 'Technical').strip(),
                    level=item.get('level', 'Beginner').strip(),
                    url=item.get('url', '#').strip(),
                    duration_hours=float(item.get('duration_hours', 10.0)),
                    difficulty=item.get('difficulty', 'Moderate').strip(),
                    rating=float(item['rating']) if item.get('rating') is not None else None,
                    language=item.get('language', 'English').strip(),
                    is_free=bool(item.get('is_free', True)),
                    is_active=bool(item.get('is_active', True)),
                    resource_type=item.get('resource_type', 'Course').strip()
                )
                course.set_topics(item.get('topics', []))
                db.session.add(course)
                seeded_count += 1

            db.session.commit()
            print(f"[+] Successfully seeded {seeded_count} curated courses into database.")
            return seeded_count
        except Exception as e:
            db.session.rollback()
            print(f"[-] Error seeding courses database: {e}")
            return 0

    def generate_recommendations(self, user=None, target_role=None, force_refresh=False):
        """
        Main recommendation pipeline:
        1. Runs/retrieves Skill Gap Analysis for user & target career.
        2. Identifies user's skill gaps (MISSING, PARTIAL), missing topics, and velocity.
        3. Matches and scores courses in the database against identified gaps using multi-factor algorithm.
        4. Dynamically builds 'Why This Course?' justifications and topic match breakdowns.
        5. Sequences an ordered learning plan preview.
        6. Persists/updates recommendations to SQLite.
        """
        # Ensure courses are seeded
        self.seed_courses_if_empty()

        # 1. Run or fetch Skill Gap Analysis
        analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        target_role_display = analysis.get('target_role', 'Data Analyst')
        is_custom_role = analysis.get('is_custom_role', False)
        market_status = analysis.get('market_status', 'Verified Industry Benchmark')

        # 2. Extract gap items map
        gap_items = analysis.get('gap_items', [])
        gap_map = {}
        for g in gap_items:
            canonical_name, _ = normalize_skill(g['skill_name'])
            gap_map[canonical_name] = g

        # 3. User learning preferences & velocity
        profile = user.user_profile if user else None
        weekly_hours = 10.0
        user_preferences = []
        preferred_difficulty = 'Balanced'

        if profile:
            if profile.learning_hours_per_week and profile.learning_hours_per_week > 0:
                weekly_hours = float(profile.learning_hours_per_week)
            user_preferences = profile.get_learning_preferences() or []
            preferred_difficulty = profile.preferred_difficulty or 'Balanced'

        # 4. Fetch all active courses from DB
        courses = Course.query.filter_by(is_active=True).all()
        if not courses:
            return {
                'target_role': target_role_display,
                'is_custom_role': is_custom_role,
                'market_status': market_status,
                'readiness_score': analysis.get('readiness_score', 0),
                'skills_to_improve_count': analysis.get('missing_count', 0) + analysis.get('partial_count', 0),
                'weekly_hours': weekly_hours,
                'recommendations': [],
                'completed_recommendations': [],
                'in_progress_recommendations': [],
                'learning_plan_preview': [],
                'gap_summary_explanation': self._generate_gap_summary_explanation(target_role_display, gap_items, is_custom_role),
                'fallback_skills': []
            }

        # 5. Fetch existing user recommendations if user is logged in
        existing_recs_map = {}
        if user and not force_refresh:
            existing = UserCourseRecommendation.query.filter_by(user_id=user.id).all()
            for r in existing:
                existing_recs_map[r.course_id] = r

        # 6. Score each course against user skill gaps
        scored_courses = []
        matched_skills_set = set()

        for course in courses:
            canonical_course_skill, _ = normalize_skill(course.skill)
            
            # Check if this course skill matches any skill gap item
            matched_gap = gap_map.get(canonical_course_skill)
            if not matched_gap:
                for g_can, g_info in gap_map.items():
                    if skills_match(g_can, canonical_course_skill):
                        matched_gap = g_info
                        break

            # Calculate match score & details
            score_data = self._calculate_course_recommendation_score(
                course=course,
                gap_item=matched_gap,
                user_preferences=user_preferences,
                weekly_hours=weekly_hours,
                preferred_difficulty=preferred_difficulty,
                target_role=target_role_display
            )

            # Check if user already marked status for this recommendation
            existing_rec = existing_recs_map.get(course.id)
            current_status = existing_rec.status if existing_rec else 'Recommended'

            course_dict = course.to_dict()
            course_dict.update({
                'recommendation_score': score_data['score'],
                'priority': score_data['priority'],
                'why_recommended': score_data['why_recommended'],
                'gap_status': score_data['gap_status'],
                'gap_priority': score_data['gap_priority'],
                'user_level': score_data['user_level'],
                'required_level': score_data['required_level'],
                'estimated_weeks': score_data['estimated_weeks'],
                'topics_you_need': score_data['topics_you_need'],
                'topics_covered': score_data['topics_covered'],
                'matched_topics': score_data['matched_topics'],
                'topic_match_percent': score_data['topic_match_percent'],
                'status': current_status,
                'is_gap_skill': matched_gap is not None and matched_gap['status'] in ['MISSING', 'PARTIAL']
            })

            # Only include if it has relevant gap value or is a high-value domain skill
            if score_data['is_relevant']:
                scored_courses.append(course_dict)
                if matched_gap:
                    matched_skills_set.add(canonical_course_skill)

        # 7. Sort recommendations by default (Best Match: score desc, then priority desc)
        priority_rank = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        scored_courses.sort(
            key=lambda x: (x.get('is_gap_skill', False), priority_rank.get(x['priority'], 1), x['recommendation_score']),
            reverse=True
        )

        # 8. Identify fallback skills (required skills with no matching course in DB)
        fallback_skills = []
        for g_can, g_info in gap_map.items():
            if g_info['status'] in ['MISSING', 'PARTIAL'] and g_can not in matched_skills_set:
                fallback_skills.append({
                    'skill_name': g_info['skill_name'],
                    'importance': g_info['importance'],
                    'status': g_info['status'],
                    'required_level': g_info['required_level'],
                    'remaining_topics': g_info.get('remaining_topics', []),
                    'suggested_project': f"Real-world hands-on project utilizing {g_info['skill_name']} for {target_role_display}",
                    'suggested_docs_url': f"https://www.google.com/search?q={g_info['skill_name'].replace(' ', '+')}+documentation+tutorial"
                })

        # 9. Generate Ordered Learning Plan Preview
        learning_plan_preview = self._generate_learning_plan_preview(scored_courses, gap_items)

        # 10. Persist recommendations to SQLite for user
        if user:
            self._save_user_recommendations_to_db(user.id, scored_courses)

        # Separate into active, in-progress, and completed
        active_recommendations = [c for c in scored_courses if c['status'] in ['Recommended', 'Saved']]
        in_progress_recommendations = [c for c in scored_courses if c['status'] == 'In Progress']
        completed_recommendations = [c for c in scored_courses if c['status'] == 'Completed']

        skills_to_improve = [g for g in gap_items if g['status'] in ['MISSING', 'PARTIAL']]

        return {
            'target_role': target_role_display,
            'is_custom_role': is_custom_role,
            'market_status': market_status,
            'readiness_score': analysis.get('readiness_score', 0),
            'skills_to_improve_count': len(skills_to_improve),
            'weekly_hours': weekly_hours,
            'recommendations': scored_courses,
            'active_recommendations': active_recommendations,
            'in_progress_recommendations': in_progress_recommendations,
            'completed_recommendations': completed_recommendations,
            'learning_plan_preview': learning_plan_preview,
            'gap_summary_explanation': self._generate_gap_summary_explanation(target_role_display, gap_items, is_custom_role),
            'fallback_skills': fallback_skills
        }

    def _calculate_course_recommendation_score(self, course, gap_item, user_preferences, weekly_hours, preferred_difficulty, target_role):
        """
        Multi-factor recommendation scoring:
        1. Skill Gap Weight (35%)
        2. Career Importance (20%)
        3. Topic Match Overlap (20%)
        4. Proficiency & Level Match (15%)
        5. Learning Preference & Velocity Match (10%)
        """
        score = 40.0  # Baseline
        gap_status = 'NO GAP'
        gap_priority = 'Low'
        user_level = 'No Knowledge'
        required_level = 'Intermediate'
        is_relevant = True

        topics_you_need = []
        topics_covered = course.get_topics() or []
        matched_topics = []
        topic_match_percent = 0

        # 1. Skill Gap Weight (0 - 35 pts)
        if gap_item:
            gap_status = gap_item.get('status', 'MISSING')
            gap_priority = gap_item.get('priority', 'Medium')
            user_level = gap_item.get('user_level', 'No Knowledge')
            required_level = gap_item.get('required_level', 'Intermediate')
            topics_you_need = gap_item.get('remaining_topics') or gap_item.get('all_topics') or []

            if gap_status == 'MISSING':
                score += 35.0
            elif gap_status == 'PARTIAL':
                score += 26.0
            elif gap_status == 'STRONG':
                score += 5.0
            else:
                score += 8.0
        else:
            # Not an explicit target career skill
            score += 0.0
            is_relevant = False

        # 2. Career Importance Weight (0 - 20 pts)
        if gap_item:
            imp = gap_item.get('importance', 'Medium')
            if imp == 'Critical':
                score += 20.0
            elif imp == 'High':
                score += 15.0
            elif imp == 'Medium':
                score += 10.0
            else:
                score += 5.0

        # 3. Topic Match Overlap (0 - 20 pts)
        if topics_you_need and topics_covered:
            for need_t in topics_you_need:
                need_name = need_t.get('name', '') if isinstance(need_t, dict) else str(need_t)
                need_clean = re.sub(r'[^a-zA-Z0-9]', '', need_name).lower()
                for cov_t in topics_covered:
                    cov_name = cov_t.get('name', '') if isinstance(cov_t, dict) else str(cov_t)
                    cov_clean = re.sub(r'[^a-zA-Z0-9]', '', cov_name).lower()
                    if (need_clean and cov_clean) and (need_clean in cov_clean or cov_clean in need_clean or 
                        SequenceMatcher(None, need_clean, cov_clean).ratio() > 0.65):
                        if need_name not in matched_topics:
                            matched_topics.append(need_name)
                        break

            if topics_you_need:
                topic_ratio = len(matched_topics) / max(1, len(topics_you_need))
                score += min(20.0, topic_ratio * 20.0)
                topic_match_percent = int(topic_ratio * 100)
        elif gap_item and gap_item.get('status') in ['MISSING', 'PARTIAL']:
            score += 12.0
            topic_match_percent = 75

        # 4. Proficiency & Level Appropriateness (0 - 15 pts)
        course_level = course.level or 'Beginner'
        if user_level in ['No Knowledge', 'Beginner']:
            if course_level == 'Beginner':
                score += 15.0
            elif course_level == 'All Levels':
                score += 13.0
            elif course_level == 'Intermediate':
                score += 10.0
            else:
                score += 4.0
        elif user_level == 'Intermediate':
            if course_level in ['Intermediate', 'Advanced']:
                score += 15.0
            elif course_level == 'All Levels':
                score += 12.0
            else:
                score += 6.0
        elif user_level == 'Advanced':
            if course_level == 'Advanced' or course.resource_type == 'Project':
                score += 15.0
            else:
                score += 8.0

        # 5. User Learning Preferences & Duration (0 - 10 pts)
        res_type = course.resource_type or 'Course'
        pref_boost = 0.0
        for pref in user_preferences:
            p_lower = pref.lower()
            if 'video' in p_lower and res_type in ['Course', 'Tutorial']:
                pref_boost += 3.0
            if 'practice' in p_lower and res_type in ['Practice', 'Project']:
                pref_boost += 4.0
            if 'project' in p_lower and res_type == 'Project':
                pref_boost += 4.0
            if 'doc' in p_lower and res_type == 'Documentation':
                pref_boost += 3.0
            if 'cert' in p_lower and res_type == 'Certification':
                pref_boost += 4.0

        score += min(6.0, pref_boost)

        # Estimated completion calculation
        duration = course.duration_hours or 10.0
        effective_weekly = max(1.0, weekly_hours)
        estimated_weeks = max(1, math.ceil(duration / effective_weekly))
        if duration <= 25.0:
            score += 4.0
        else:
            score += 2.0

        # Clamp recommendation score between 35% and 99%
        final_score = int(min(99, max(35, score)))

        # Priority categorization
        if gap_item:
            if gap_item.get('importance') == 'Critical' and gap_status in ['MISSING', 'PARTIAL']:
                priority = 'CRITICAL'
            elif gap_item.get('importance') == 'High' or final_score >= 82:
                priority = 'HIGH'
            elif gap_item.get('importance') == 'Medium' or final_score >= 68:
                priority = 'MEDIUM'
            else:
                priority = 'LOW'
        else:
            priority = 'LOW'

        # Generate contextual "Why Recommended" explanation
        why_recommended = self._generate_why_recommended_text(
            course=course,
            gap_item=gap_item,
            user_level=user_level,
            required_level=required_level,
            target_role=target_role,
            matched_topics=matched_topics,
            user_preferences=user_preferences,
            estimated_weeks=estimated_weeks
        )

        return {
            'score': final_score,
            'priority': priority,
            'why_recommended': why_recommended,
            'gap_status': gap_status,
            'gap_priority': gap_priority,
            'user_level': user_level,
            'required_level': required_level,
            'estimated_weeks': estimated_weeks,
            'topics_you_need': topics_you_need,
            'topics_covered': topics_covered,
            'matched_topics': matched_topics,
            'topic_match_percent': topic_match_percent,
            'is_relevant': is_relevant
        }

    def _generate_why_recommended_text(self, course, gap_item, user_level, required_level, target_role, matched_topics, user_preferences, estimated_weeks):
        """Generates dynamic, transparent, human-readable justification for recommendation."""
        reasons = []
        skill_name = course.skill

        if gap_item:
            imp = gap_item.get('importance', 'High')
            status = gap_item.get('status', 'MISSING')
            
            if status == 'MISSING':
                reasons.append(f"**{skill_name}** is a **{imp}** requirement for **{target_role}** roles and you have not logged prior experience in this area.")
            elif status == 'PARTIAL':
                reasons.append(f"**{skill_name}** is required at **{required_level}** level for **{target_role}**, while your current proficiency is **{user_level}**.")
            elif status == 'STRONG':
                reasons.append(f"Reinforces and polishes your strong background in **{skill_name}** with advanced practice.")
        else:
            reasons.append(f"Covers valuable core data analytics and problem-solving skills for modern tech roles.")

        if matched_topics:
            topic_names = ", ".join(matched_topics[:3])
            reasons.append(f"Directly teaches missing topics you need: **{topic_names}**.")

        # Learning preference match
        matched_prefs = []
        for pref in user_preferences:
            if 'practice' in pref.lower() and course.resource_type in ['Practice', 'Project']:
                matched_prefs.append("hands-on practice")
            elif 'video' in pref.lower() and course.resource_type in ['Course', 'Tutorial']:
                matched_prefs.append("structured video courses")
            elif 'project' in pref.lower() and course.resource_type == 'Project':
                matched_prefs.append("portfolio projects")

        if matched_prefs:
            reasons.append(f"Aligned with your preference for **{', '.join(set(matched_prefs))}**.")

        week_text = f"{estimated_weeks} week" if estimated_weeks == 1 else f"{estimated_weeks} weeks"
        reasons.append(f"Estimated completion: ~**{week_text}**.")

        return " ".join(reasons)

    def _generate_gap_summary_explanation(self, target_role, gap_items, is_custom_role):
        """Generates high-level synthesis explanation banner for the recommendation page."""
        critical_gaps = [g['skill_name'] for g in gap_items if g['importance'] == 'Critical' and g['status'] in ['MISSING', 'PARTIAL']]
        high_gaps = [g['skill_name'] for g in gap_items if g['importance'] == 'High' and g['status'] in ['MISSING', 'PARTIAL']]

        top_gaps = critical_gaps + high_gaps
        if not top_gaps:
            top_gaps = [g['skill_name'] for g in gap_items if g['status'] in ['MISSING', 'PARTIAL']][:3]

        if not top_gaps:
            return f"You meet or exceed the required skills for **{target_role}**. We recommend advanced projects and certifications to stand out to employers."

        gaps_str = " and ".join([f"**{g}**" for g in top_gaps[:2]])
        
        custom_clause = ""
        if is_custom_role:
            custom_clause = " Recommendations are synthesized based on related market roles."

        return (
            f"You selected **{target_role}** as your target career.{custom_clause} "
            f"Based on your profile and verified market requirements, {gaps_str} "
            f"are your highest-priority skill gaps. We recommend mastering these high-impact areas first "
            f"before progressing to secondary tools."
        )

    def _generate_learning_plan_preview(self, scored_courses, gap_items):
        """Generates an ordered sequential curriculum from foundational gaps to capstones."""
        plan = []
        seen_skills = set()

        # Step 1: Critical & High Priority Foundations (Beginner Courses & Practice)
        for c in scored_courses:
            if c['priority'] in ['CRITICAL', 'HIGH'] and c['level'] in ['Beginner', 'All Levels'] and c['resource_type'] in ['Course', 'Tutorial', 'Practice']:
                if c['skill'] not in seen_skills:
                    plan.append({
                        'step': len(plan) + 1,
                        'title': f"{c['skill']} Fundamentals & Core Syntax",
                        'course_title': c['title'],
                        'course_id': c['id'],
                        'provider': c['provider'],
                        'skill': c['skill'],
                        'duration_hours': c['duration_hours'],
                        'resource_type': c['resource_type'],
                        'category': 'Foundations'
                    })
                    seen_skills.add(c['skill'])

        # Step 2: Intermediate Tools & Analysis
        for c in scored_courses:
            if c['priority'] in ['CRITICAL', 'HIGH'] and c['level'] in ['Intermediate'] and c['resource_type'] in ['Course', 'Tutorial']:
                key = f"{c['skill']}_intermediate"
                if key not in seen_skills:
                    plan.append({
                        'step': len(plan) + 1,
                        'title': f"Intermediate {c['skill']} & Data Manipulation",
                        'course_title': c['title'],
                        'course_id': c['id'],
                        'provider': c['provider'],
                        'skill': c['skill'],
                        'duration_hours': c['duration_hours'],
                        'resource_type': c['resource_type'],
                        'category': 'Core Tool Mastery'
                    })
                    seen_skills.add(key)

        # Step 3: Advanced Optimization & Secondary Skills
        for c in scored_courses:
            if c['level'] in ['Advanced'] or c['priority'] in ['MEDIUM']:
                key = f"{c['skill']}_advanced"
                if key not in seen_skills and len(plan) < 7:
                    plan.append({
                        'step': len(plan) + 1,
                        'title': f"Advanced {c['skill']} & Industry Techniques",
                        'course_title': c['title'],
                        'course_id': c['id'],
                        'provider': c['provider'],
                        'skill': c['skill'],
                        'duration_hours': c['duration_hours'],
                        'resource_type': c['resource_type'],
                        'category': 'Advanced Analytics'
                    })
                    seen_skills.add(key)

        # Step 4: Capstone Portfolio Projects
        for c in scored_courses:
            if c['resource_type'] == 'Project' and len(plan) < 8:
                plan.append({
                    'step': len(plan) + 1,
                    'title': f"Real-World {c['skill']} Capstone Portfolio Project",
                    'course_title': c['title'],
                    'course_id': c['id'],
                    'provider': c['provider'],
                    'skill': c['skill'],
                    'duration_hours': c['duration_hours'],
                    'resource_type': c['resource_type'],
                    'category': 'Portfolio Project'
                })
                break

        return plan

    def _save_user_recommendations_to_db(self, user_id, scored_courses):
        """Persists or updates UserCourseRecommendation rows in SQLite."""
        try:
            for item in scored_courses:
                course_id = item['id']
                rec = UserCourseRecommendation.query.filter_by(user_id=user_id, course_id=course_id).first()
                if not rec:
                    rec = UserCourseRecommendation(
                        user_id=user_id,
                        course_id=course_id,
                        recommendation_score=item['recommendation_score'],
                        priority=item['priority'],
                        status='Recommended',
                        why_recommended=item['why_recommended'],
                        estimated_weeks=item['estimated_weeks']
                    )
                    rec.set_matched_topics(item.get('matched_topics', []))
                    db.session.add(rec)
                else:
                    # Update recommendation score and why_recommended
                    rec.recommendation_score = item['recommendation_score']
                    rec.priority = item['priority']
                    rec.why_recommended = item['why_recommended']
                    rec.estimated_weeks = item['estimated_weeks']
                    rec.set_matched_topics(item.get('matched_topics', []))

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[-] Error persisting user course recommendations: {e}")

    def update_recommendation_status(self, user_id, course_id, status):
        """Updates recommendation status (e.g., 'In Progress', 'Completed', 'Saved', 'Skipped')."""
        try:
            rec = UserCourseRecommendation.query.filter_by(user_id=user_id, course_id=course_id).first()
            if not rec:
                # Create record if not exists
                course = db.session.get(Course, course_id)
                if not course:
                    return {'success': False, 'error': 'Course not found'}
                rec = UserCourseRecommendation(
                    user_id=user_id,
                    course_id=course_id,
                    status=status
                )
                db.session.add(rec)

            rec.status = status
            now = datetime.now(timezone.utc)
            if status == 'In Progress' and not rec.started_at:
                rec.started_at = now
            elif status == 'Completed':
                rec.completed_at = now

            db.session.commit()
            return {'success': True, 'status': status, 'course_id': course_id}
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}


recommendation_service = RecommendationService()
