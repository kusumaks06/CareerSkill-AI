import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
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
    AssessmentQuestion, 
    AssessmentAttempt, 
    AssessmentAnswer,
    CourseProgress,
    LearningActivity,
    SkillProgressHistory,
    PROFICIENCY_SCORE_MAP
)
from services.skill_normalizer import normalize_skill, skills_match
from services.skill_gap_service import skill_gap_service
from services.recommendation_service import recommendation_service
from services.roadmap_service import roadmap_service

QUESTIONS_FILE = Path(__file__).resolve().parent.parent / 'data' / 'assessment_questions.json'


class AssessmentService:
    """
    Intelligent Skill Assessment & Progress Validation Engine.
    Handles adaptive question selection, scoring, topic diagnostics,
    three-way calibration, retake tracking, and cascading synchronization.
    """

    def __init__(self, questions_path: Optional[Path] = None):
        self.questions_path = questions_path or QUESTIONS_FILE

    def seed_questions_if_empty(self) -> int:
        """Populates the assessment_questions table with curated technical questions if empty."""
        try:
            count = AssessmentQuestion.query.count()
            if count > 0:
                return count

            if not self.questions_path.exists():
                return 0

            with open(self.questions_path, 'r', encoding='utf-8') as f:
                questions_data = json.load(f)

            added_count = 0
            for item in questions_data:
                q = AssessmentQuestion(
                    skill=item.get('skill', 'SQL'),
                    topic=item.get('topic', 'General'),
                    difficulty=item.get('difficulty', 'Intermediate'),
                    question_type=item.get('question_type', 'multiple_choice'),
                    question_text=item.get('question_text', ''),
                    correct_answer=item.get('correct_answer', ''),
                    explanation=item.get('explanation', ''),
                    is_active=True
                )
                q.set_options(item.get('options', []))
                db.session.add(q)
                added_count += 1

            db.session.commit()
            print(f"[+] Successfully seeded {added_count} assessment questions into database.")
            return added_count
        except Exception as e:
            db.session.rollback()
            print(f"[-] Assessment question seeding error: {e}")
            return 0

    def get_available_assessment_skills(self, user: Optional[User] = None, target_role: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns list of skills available for assessment, enriched with user validation status,
        last score, and priority ranking based on target career requirements.
        """
        # Get canonical distinct skills present in the questions bank
        all_skills_query = db.session.query(AssessmentQuestion.skill).filter_by(is_active=True).distinct().all()
        distinct_skills = [s[0] for s in all_skills_query] if all_skills_query else ['SQL', 'Python', 'Excel', 'Power BI', 'Statistics', 'Machine Learning', 'Tableau']

        # Determine target role and required skills
        role_skills = []
        if user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            target_role = target_role or (tc.career_name if tc else 'Data Analyst')
        else:
            target_role = target_role or 'Data Analyst'

        # Get market skills from skill gap service
        analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        gap_items = analysis.get('gap_items', [])
        gap_skills_map = {item['normalized_skill_name'].lower(): item for item in gap_items}

        skills_list = []
        for skill_name in distinct_skills:
            canonical_name, _ = normalize_skill(skill_name)
            gap_info = gap_skills_map.get(canonical_name.lower())

            # Query user's latest assessment attempt for this skill
            latest_attempt = None
            if user:
                latest_attempt = AssessmentAttempt.query.filter_by(
                    user_id=user.id,
                    skill_name=canonical_name
                ).order_by(AssessmentAttempt.id.desc()).first()

            # Self-reported level
            self_reported_level = "Beginner"
            if user:
                user_skill = UserSkill.query.filter_by(user_id=user.id).all()
                for us in user_skill:
                    if skills_match(us.skill_name, canonical_name):
                        self_reported_level = us.proficiency_level
                        break
            elif gap_info:
                self_reported_level = gap_info.get('user_level', 'Beginner')

            # Validation status
            if latest_attempt:
                score = latest_attempt.score
                if score >= 70:
                    validation_status = "Validated"
                    status_badge = "success"
                else:
                    validation_status = "Needs Improvement"
                    status_badge = "warning"
                last_score = round(score, 1)
                assessed_level = latest_attempt.assessed_level
            else:
                validation_status = "Not Assessed"
                status_badge = "secondary"
                last_score = None
                assessed_level = None

            is_required_for_career = gap_info is not None
            required_level = gap_info.get('required_level', 'Intermediate') if gap_info else 'Intermediate'
            priority = gap_info.get('priority', 'Medium') if gap_info else 'Medium'

            skills_list.append({
                'skill_name': canonical_name,
                'is_required_for_career': is_required_for_career,
                'required_level': required_level,
                'self_reported_level': self_reported_level,
                'priority': priority,
                'validation_status': validation_status,
                'status_badge': status_badge,
                'last_score': last_score,
                'assessed_level': assessed_level,
                'latest_attempt_id': latest_attempt.id if latest_attempt else None,
                'question_count': AssessmentQuestion.query.filter_by(skill=canonical_name, is_active=True).count()
            })

        # Sort: Required for target career first (by priority), then by name
        priority_rank = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
        skills_list.sort(key=lambda x: (
            0 if x['is_required_for_career'] else 1,
            priority_rank.get(x['priority'], 9),
            x['skill_name']
        ))

        return skills_list

    def generate_assessment(
        self, 
        user: Optional[User] = None, 
        skill_name: str = 'SQL', 
        target_role: Optional[str] = None, 
        difficulty: Optional[str] = None, 
        num_questions: int = 8
    ) -> Dict[str, Any]:
        """
        Generates an adaptive question set for a skill assessment.
        Selects questions tailored to user's proficiency tier and missing syllabus topics.
        """
        self.seed_questions_if_empty()
        canonical_name, _ = normalize_skill(skill_name)

        # Determine user self-reported proficiency level
        user_level = 'Beginner'
        if user:
            user_skills = UserSkill.query.filter_by(user_id=user.id).all()
            for us in user_skills:
                if skills_match(us.skill_name, canonical_name):
                    user_level = us.proficiency_level
                    break

        assessed_difficulty = difficulty or user_level
        if assessed_difficulty not in ['Beginner', 'Intermediate', 'Advanced']:
            assessed_difficulty = 'Intermediate'

        # Fetch questions from database
        query = AssessmentQuestion.query.filter(
            AssessmentQuestion.skill.ilike(f"%{canonical_name}%"),
            AssessmentQuestion.is_active == True
        )

        all_skill_questions = query.all()

        if not all_skill_questions:
            # Fallback to any active questions if none specific
            all_skill_questions = AssessmentQuestion.query.filter_by(is_active=True).limit(num_questions).all()

        # Prioritize matching difficulty + adjacent difficulty
        matched_questions = [q for q in all_skill_questions if q.difficulty.lower() == assessed_difficulty.lower()]
        other_questions = [q for q in all_skill_questions if q.difficulty.lower() != assessed_difficulty.lower()]

        selected = (matched_questions + other_questions)[:num_questions]

        # Convert to serialized representation (without correct answers for client-side security)
        questions_payload = [q.to_dict(include_correct=False) for q in selected]

        return {
            'skill_name': canonical_name,
            'target_role': target_role or 'Data Analyst',
            'difficulty': assessed_difficulty,
            'user_level': user_level,
            'total_questions': len(questions_payload),
            'questions': questions_payload
        }

    def evaluate_assessment(
        self, 
        user: Optional[User] = None, 
        skill_name: str = 'SQL', 
        answers_dict: Optional[Dict[str, str]] = None, 
        target_role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates submitted assessment answers, computes topic mastery,
        conducts three-way comparison (Self-Reported vs Assessed vs Market Required),
        tracks retake improvement, and triggers cascading updates.
        """
        answers_dict = answers_dict or {}
        canonical_name, _ = normalize_skill(skill_name)
        target_role = target_role or 'Data Analyst'

        # 1. Fetch Question objects and evaluate each answer
        total_questions = 0
        correct_count = 0
        incorrect_count = 0
        evaluated_answers = []
        topic_stats = {}

        for q_id_raw, user_ans in answers_dict.items():
            try:
                q_id = int(q_id_raw)
            except (ValueError, TypeError):
                continue

            question = db.session.get(AssessmentQuestion, q_id)
            if not question:
                continue

            total_questions += 1
            is_correct = (str(user_ans).strip().lower() == str(question.correct_answer).strip().lower())
            
            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1

            topic = question.topic or 'General'
            if topic not in topic_stats:
                topic_stats[topic] = {'correct': 0, 'total': 0}
            topic_stats[topic]['total'] += 1
            if is_correct:
                topic_stats[topic]['correct'] += 1

            evaluated_answers.append({
                'question_id': question.id,
                'topic': topic,
                'user_answer': user_ans,
                'correct_answer': question.correct_answer,
                'is_correct': is_correct,
                'question_text': question.question_text,
                'explanation': question.explanation,
                'difficulty': question.difficulty
            })

        # Calculate score %
        if total_questions > 0:
            score = round((correct_count / total_questions) * 100, 1)
        else:
            score = 0.0

        # 2. Topic Classification: Strong vs Needs Improvement
        strong_topics = []
        weak_topics = []

        for topic, stat in topic_stats.items():
            topic_acc = stat['correct'] / stat['total']
            if topic_acc >= 0.70:
                strong_topics.append(topic)
            else:
                weak_topics.append(topic)

        # 3. Assessed Skill Level Determination
        if score >= 90:
            assessed_level = "Expert"
            assessed_score = 100
        elif score >= 70:
            assessed_level = "Advanced"
            assessed_score = 75
        elif score >= 45:
            assessed_level = "Intermediate"
            assessed_score = 50
        elif score >= 20:
            assessed_level = "Beginner"
            assessed_score = 25
        else:
            assessed_level = "Beginner"
            assessed_score = 25

        # 4. Determine Self-Reported and Market Required Benchmarks
        self_reported_level = "Beginner"
        self_reported_score = 25

        if user:
            user_skill_records = UserSkill.query.filter_by(user_id=user.id).all()
            for us in user_skill_records:
                if skills_match(us.skill_name, canonical_name):
                    self_reported_level = us.proficiency_level
                    self_reported_score = us.proficiency_score
                    break

        # Market requirement from gap analysis
        gap_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        gap_items = gap_analysis.get('gap_items', [])
        market_item = next((i for i in gap_items if skills_match(i['skill_name'], canonical_name)), None)

        if market_item:
            market_required_level = market_item.get('required_level', 'Intermediate')
            market_required_score = market_item.get('required_score', 50)
        else:
            market_required_level = 'Intermediate'
            market_required_score = 50

        # 5. Three-Way Comparison Verdict
        if assessed_score < self_reported_score:
            comparison_verdict = (
                f"Your assessment indicates that your current {canonical_name} proficiency "
                f"may be lower than your self-reported {self_reported_level} level. "
                f"Reviewing the identified weak topics will quickly elevate your practical capability."
            )
        elif assessed_score >= market_required_score:
            comparison_verdict = (
                f"Outstanding! Your verified {canonical_name} score ({score}%) meets or exceeds "
                f"the industry benchmark ({market_required_level}) required for {target_role}."
            )
        elif assessed_score > self_reported_score:
            comparison_verdict = (
                f"Great job! Your assessed {canonical_name} performance ({assessed_level}) "
                f"demonstrates stronger proficiency than your initial self-reported baseline ({self_reported_level})."
            )
        else:
            comparison_verdict = (
                f"Good effort! You demonstrated understanding in core areas. Focusing on "
                f"{len(weak_topics)} improvement topic(s) will bridge your gap to the required {market_required_level} level."
            )

        # 6. Retake Improvement Tracking
        previous_score = None
        score_improvement = None

        if user:
            prior_attempt = AssessmentAttempt.query.filter_by(
                user_id=user.id,
                skill_name=canonical_name
            ).order_by(AssessmentAttempt.id.desc()).first()

            if prior_attempt:
                previous_score = prior_attempt.score
                score_improvement = round(score - previous_score, 1)

        # 7. Persist AssessmentAttempt and AssessmentAnswer to SQLite
        attempt = None
        if user:
            attempt = AssessmentAttempt(
                user_id=user.id,
                skill_name=canonical_name,
                target_role=target_role,
                difficulty=assessed_level,
                total_questions=total_questions,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                score=score,
                self_reported_level=self_reported_level,
                self_reported_score=self_reported_score,
                assessed_level=assessed_level,
                assessed_score=assessed_score,
                market_required_level=market_required_level,
                market_required_score=market_required_score,
                comparison_verdict=comparison_verdict,
                previous_score=previous_score,
                score_improvement=score_improvement
            )
            attempt.set_strong_topics(strong_topics)
            attempt.set_weak_topics(weak_topics)
            db.session.add(attempt)
            db.session.flush()

            for ans in evaluated_answers:
                answer_record = AssessmentAnswer(
                    attempt_id=attempt.id,
                    question_id=ans['question_id'],
                    topic=ans['topic'],
                    user_answer=str(ans['user_answer']),
                    correct_answer=str(ans['correct_answer']),
                    is_correct=ans['is_correct']
                )
                db.session.add(answer_record)

            db.session.commit()

            # 8. CASCADING UPDATES ACROSS MODULES
            self._apply_cascading_updates(
                user=user,
                skill_name=canonical_name,
                assessed_level=assessed_level,
                assessed_score=assessed_score,
                strong_topics=strong_topics,
                weak_topics=weak_topics,
                target_role=target_role
            )

        return {
            'attempt_id': attempt.id if attempt else 1,
            'skill_name': canonical_name,
            'target_role': target_role,
            'score': score,
            'total_questions': total_questions,
            'correct_count': correct_count,
            'incorrect_count': incorrect_count,
            'assessed_level': assessed_level,
            'assessed_score': assessed_score,
            'self_reported_level': self_reported_level,
            'self_reported_score': self_reported_score,
            'market_required_level': market_required_level,
            'market_required_score': market_required_score,
            'comparison_verdict': comparison_verdict,
            'previous_score': previous_score,
            'score_improvement': score_improvement,
            'strong_topics': strong_topics,
            'weak_topics': weak_topics,
            'evaluated_answers': evaluated_answers
        }

    def _apply_cascading_updates(
        self,
        user: User,
        skill_name: str,
        assessed_level: str,
        assessed_score: int,
        strong_topics: List[str],
        weak_topics: List[str],
        target_role: str
    ):
        """
        Synchronizes assessment findings across:
        1. User Profile & Skills (UserSkill)
        2. Skill Gap Analysis & Topic Gap (SkillGapAnalysis)
        3. Course Recommendations (UserCourseRecommendation)
        4. Career Roadmap Milestones & Practice Tasks (UserRoadmap)
        """
        try:
            # 1. Update UserSkill
            user_skill = UserSkill.query.filter_by(user_id=user.id).all()
            target_skill_record = None
            for us in user_skill:
                if skills_match(us.skill_name, skill_name):
                    target_skill_record = us
                    break

            prev_score = target_skill_record.proficiency_score if target_skill_record else 25

            if target_skill_record:
                target_skill_record.proficiency_level = assessed_level
                target_skill_record.proficiency_score = assessed_score
            else:
                new_skill = UserSkill(
                    user_id=user.id,
                    skill_name=skill_name,
                    proficiency_level=assessed_level,
                    proficiency_score=assessed_score,
                    confidence_level=4 if assessed_score >= 50 else 2
                )
                db.session.add(new_skill)

            # Record Skill Progress History
            sph = SkillProgressHistory(
                user_id=user.id,
                skill_name=skill_name,
                previous_score=prev_score,
                current_score=assessed_score,
                target_score=75,
                triggered_by='Assessment'
            )
            db.session.add(sph)

            # Record Learning Activity
            act = LearningActivity(
                user_id=user.id,
                activity_type='Assessment',
                title=f"{skill_name} Assessment ({assessed_level})",
                skill=skill_name,
                hours=0.5,
                score=float(assessed_score),
                progress_delta=float(max(0, assessed_score - prev_score)),
                notes=f"{len(strong_topics)} strong topics, {len(weak_topics)} weak topics identified."
            )
            db.session.add(act)

            # 2. Update SkillGapAnalysis Topic Evaluations
            saved_analysis = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first()
            topic_evals = saved_analysis.get_topic_evaluations() if saved_analysis else {}

            # Set verified strong topics as known topics
            existing_known = topic_evals.get(skill_name, [])
            updated_known = list(set(existing_known + strong_topics) - set(weak_topics))
            topic_evals[skill_name] = updated_known

            # Recalculate full gap analysis and persist to DB
            fresh_analysis = skill_gap_service.analyze_skill_gap(
                user=user,
                target_role=target_role,
                custom_topic_evaluations=topic_evals
            )
            skill_gap_service.save_analysis_to_db(user.id, fresh_analysis)

            # 3. Refresh Course Recommendations for Weak Topics
            recommendation_service.generate_recommendations(user=user, target_role=target_role)

            # 4. Update Roadmap: Escalate priority for weak topics
            roadmap = UserRoadmap.query.filter_by(user_id=user.id).first()
            if roadmap and weak_topics:
                # Find or add practice tasks for weak topics in corresponding milestone
                for m in roadmap.milestones:
                    if skills_match(m.skill, skill_name):
                        m.priority = 'Critical'
                        current_tasks = m.get_tasks()
                        for wt in weak_topics:
                            task_name = f"Reinforce {wt} (Identified in Skill Assessment)"
                            if not any(t.get('task') == task_name for t in current_tasks):
                                current_tasks.append({
                                    'task': task_name,
                                    'completed': False,
                                    'priority': 'Critical',
                                    'estimated_hours': 4.0,
                                    'type': 'Assessment Remediation'
                                })
                        m.set_tasks(current_tasks)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[-] Cascading update error after assessment: {e}")

    def get_user_assessment_stats(self, user_id: Optional[int]) -> Dict[str, Any]:
        """Calculates dashboard summary metrics for completed assessments."""
        if not user_id:
            return {
                'total_completed': 0,
                'avg_score': 0.0,
                'validated_count': 0,
                'improvement_needed_count': 0,
                'recent_attempts': []
            }

        attempts = AssessmentAttempt.query.filter_by(user_id=user_id).order_by(AssessmentAttempt.id.desc()).all()
        
        if not attempts:
            return {
                'total_completed': 0,
                'avg_score': 0.0,
                'validated_count': 0,
                'improvement_needed_count': 0,
                'recent_attempts': []
            }

        total = len(attempts)
        avg_score = round(sum(a.score for a in attempts) / total, 1)

        # Unique skills validated (score >= 70%)
        validated_skills = set(a.skill_name for a in attempts if a.score >= 70)
        improvement_skills = set(a.skill_name for a in attempts if a.score < 70) - validated_skills

        return {
            'total_completed': total,
            'avg_score': avg_score,
            'validated_count': len(validated_skills),
            'improvement_needed_count': len(improvement_skills),
            'recent_attempts': [a.to_dict() for a in attempts[:5]]
        }


# Singleton service instance
assessment_service = AssessmentService()
