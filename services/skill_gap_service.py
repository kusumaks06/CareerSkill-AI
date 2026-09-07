import json
import math
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models import db, SkillGapAnalysis, SkillGapItem, User, UserProfile, UserSkill, TargetCareer
from services.skill_normalizer import normalize_skill, skills_match, find_matching_skill
from services.career_service import DOMAIN_SKILL_MAP

MARKET_DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'market_requirements.json'
CAREERS_DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'careers.json'

PROFICIENCY_SCORE_MAP = {
    'Beginner': 25,
    'Intermediate': 50,
    'Advanced': 75,
    'Expert': 100,
    'No Knowledge': 0,
    "I don't know this skill": 0
}

IMPORTANCE_WEIGHTS = {
    'Critical': 4,
    'High': 3,
    'Medium': 2,
    'Low': 1
}

DIFFICULTY_WEIGHTS = {
    'Easy': 1,
    'Moderate': 2,
    'Difficult': 3
}


class SkillGapService:
    """Intelligent, Data-Driven Skill Gap Analysis & Topic Decomposition Engine."""

    def __init__(self, data_path=None):
        self.data_path = data_path or MARKET_DATA_FILE
        self.careers = self._load_market_requirements()
        self._initialize_vectorizer()

    def _load_market_requirements(self):
        """Loads structured market benchmarks from JSON."""
        if not os.path.exists(self.data_path):
            return []
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('careers', [])
        except Exception as e:
            print(f"Error loading market requirements dataset: {e}")
            return []

    def _initialize_vectorizer(self):
        """Builds TF-IDF matrix for NLP-based custom role synthesis."""
        if not self.careers:
            self.vectorizer = None
            self.tfidf_matrix = None
            return

        corpus = []
        for c in self.careers:
            skill_names = [s.get('skill', '') for s in c.get('skills', [])]
            doc = (
                f"{c.get('title', '')} {c.get('normalized_title', '')} "
                f"{c.get('category', '')} {c.get('description', '')} "
                f"{' '.join(skill_names)}"
            )
            corpus.append(doc)

        self.vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def normalize_role(self, role_text):
        """Normalizes role name for consistent comparison."""
        if not role_text:
            return "", ""
        display = re.sub(r'\s+', ' ', role_text.strip())
        normalized = display.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return display, normalized

    def get_market_requirements_for_role(self, target_role):
        """
        Retrieves exact benchmark requirements or synthesizes custom role requirements
        using TF-IDF cosine similarity and domain knowledge maps.
        """
        display_title, normalized_title = self.normalize_role(target_role)
        if not normalized_title:
            display_title = "Data Analyst"
            normalized_title = "data analyst"

        # 1. Exact Match Search
        for career in self.careers:
            if career.get('normalized_title') == normalized_title:
                return {
                    'target_role': career.get('title', display_title),
                    'normalized_role': normalized_title,
                    'is_custom_role': False,
                    'market_status': 'Verified Industry Benchmark',
                    'explanation': f"Exact match found in industry market database for '{career['title']}'. Requirements reflect verified industry standards.",
                    'skills': career.get('skills', []),
                    'category': career.get('category', 'Technology')
                }

        # 2. NLP TF-IDF & Fuzzy Cosine Similarity for Custom / Hybrid Roles
        if not self.vectorizer or self.tfidf_matrix is None or not self.careers:
            # Fallback to default Data Analyst benchmark
            return self._build_fallback_requirements(display_title, normalized_title)

        query_vec = self.vectorizer.transform([f"{display_title} {normalized_title}"])
        sim_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        ranked_indices = sim_scores.argsort()[::-1]

        top_matches = []
        for idx in ranked_indices:
            score = float(sim_scores[idx])
            if score > 0.12 or len(top_matches) == 0:
                top_matches.append((self.careers[idx], score))
            if len(top_matches) >= 3:
                break

        if not top_matches or top_matches[0][1] < 0.05:
            return self._build_fallback_requirements(display_title, normalized_title)

        # Merge skills from related roles with priority weighting
        merged_skills_dict = {}
        related_titles = []

        for career, sim in top_matches:
            related_titles.append(career['title'])
            for skill_obj in career.get('skills', []):
                s_name = skill_obj.get('skill')
                canonical_name, _ = normalize_skill(s_name)
                if canonical_name not in merged_skills_dict:
                    merged_skills_dict[canonical_name] = dict(skill_obj)
                    merged_skills_dict[canonical_name]['skill'] = canonical_name

        # Domain skill enrichment
        domain_added = self._enrich_with_domain_skills(normalized_title, merged_skills_dict)

        merged_skills = list(merged_skills_dict.values())
        # Sort by importance and priority
        merged_skills.sort(key=lambda s: (
            -IMPORTANCE_WEIGHTS.get(s.get('importance', 'Medium'), 2),
            s.get('priority', 99)
        ))

        explanation = (
            f"Estimated Market Requirements synthesized from related roles ({', '.join(related_titles)}) "
            f"and specialized domain competencies."
        )
        if domain_added:
            explanation += f" Included domain skills: {', '.join(domain_added)}."

        return {
            'target_role': display_title,
            'normalized_role': normalized_title,
            'is_custom_role': True,
            'market_status': 'Estimated Market Requirements',
            'explanation': explanation,
            'skills': merged_skills,
            'category': 'Custom / Specialized Domain'
        }

    def _enrich_with_domain_skills(self, normalized_title, merged_skills_dict):
        """Enriches merged skills with domain specific skills based on title keywords."""
        domain_added = []
        for keyword, domain_skills in DOMAIN_SKILL_MAP.items():
            if keyword in normalized_title:
                for skill_name in domain_skills:
                    canonical, _ = normalize_skill(skill_name)
                    if canonical not in merged_skills_dict:
                        merged_skills_dict[canonical] = {
                            'skill': canonical,
                            'category': 'Domain',
                            'importance': 'High',
                            'required_level': 'Intermediate',
                            'estimated_hours': 35,
                            'priority': 4,
                            'difficulty': 'Moderate',
                            'topics': [
                                {'name': f'{canonical} Fundamentals', 'difficulty': 'Easy', 'hours': 8},
                                {'name': f'{canonical} Industry Methods & Standards', 'difficulty': 'Moderate', 'hours': 12},
                                {'name': f'Advanced {canonical} Case Studies', 'difficulty': 'Difficult', 'hours': 15}
                            ]
                        }
                        domain_added.append(canonical)
        return domain_added

    def _build_fallback_requirements(self, display_title, normalized_title):
        """Fallback requirements when similarity is very low or dataset is unavailable."""
        default_career = self.careers[0] if self.careers else None
        skills = default_career.get('skills', []) if default_career else []
        return {
            'target_role': display_title,
            'normalized_role': normalized_title,
            'is_custom_role': True,
            'market_status': 'Estimated Market Requirements',
            'explanation': "Limited market data available. Requirements are estimated from standard data & analytics benchmarks.",
            'skills': skills,
            'category': 'General Analytics'
        }

    def analyze_skill_gap(self, user, target_role=None, custom_topic_evaluations=None):
        """
        Executes complete Skill Gap Analysis for a user:
        1. Identifies target career requirements.
        2. Retrieves user's self-reported skills & proficiency scores.
        3. Normalizes all skill names canonically.
        4. Calculates skill-level gaps, categories (STRONG, PARTIAL, MISSING, LOW_PRIORITY).
        5. Computes topic-level gaps (known vs remaining topics, remaining hours).
        6. Computes user learning velocity, estimated weeks, and completion date.
        7. Calculates AIDS weighted Career Readiness Score (0–100%).
        8. Generates prioritized recommendations and roadmap milestones.
        """
        # 1. Resolve Target Role
        if not target_role:
            if user:
                tc = TargetCareer.query.filter_by(user_id=user.id).first()
                if tc:
                    target_role = tc.career_name
                elif user.profiles:
                    target_role = user.profiles[-1].target_role
        if not target_role:
            target_role = "Data Analyst"

        # 2. Get Market Benchmark Requirements
        market_data = self.get_market_requirements_for_role(target_role)
        required_skills = market_data.get('skills', [])

        # 3. Get User Skills Map
        user_skills_map = {}
        if user:
            user_skills = UserSkill.query.filter_by(user_id=user.id).all()
            for us in user_skills:
                canonical_name, _ = normalize_skill(us.skill_name)
                user_skills_map[canonical_name] = {
                    'original_name': us.skill_name,
                    'proficiency_level': us.proficiency_level,
                    'proficiency_score': us.proficiency_score,
                    'confidence_level': us.confidence_level
                }

        # 4. Get User Profile Learning Parameters
        profile = user.user_profile if user else None
        weekly_hours = 10.0
        if profile and profile.learning_hours_per_week:
            try:
                weekly_hours = float(profile.learning_hours_per_week)
            except (ValueError, TypeError):
                weekly_hours = 10.0
        if weekly_hours <= 0:
            weekly_hours = 10.0

        # Topic evaluations map
        topic_evaluations = custom_topic_evaluations or {}

        # 5. Perform Multi-Dimensional Skill & Topic Comparison
        gap_items = []
        total_remaining_hours = 0
        total_weighted_user_score = 0.0
        total_weighted_req_score = 0.0

        strong_count = 0
        partial_count = 0
        missing_count = 0

        for req in required_skills:
            req_skill_name = req.get('skill', '')
            canonical_req_name, clean_req_key = normalize_skill(req_skill_name)
            
            category = req.get('category', 'Technical')
            importance = req.get('importance', 'High')
            importance_weight = IMPORTANCE_WEIGHTS.get(importance, 3)
            
            req_level = req.get('required_level', 'Intermediate')
            req_score = PROFICIENCY_SCORE_MAP.get(req_level, 50)
            
            difficulty = req.get('difficulty', 'Moderate')
            est_total_hours = req.get('estimated_hours', 40)
            all_topics = req.get('topics', [])

            # Check if user has this skill
            user_skill_info = user_skills_map.get(canonical_req_name)
            if not user_skill_info:
                # Fuzzy fallback check against user skills
                for u_can_name, u_info in user_skills_map.items():
                    if skills_match(u_can_name, canonical_req_name):
                        user_skill_info = u_info
                        break

            if user_skill_info:
                user_level = user_skill_info.get('proficiency_level', 'Beginner')
                user_score = user_skill_info.get('proficiency_score', 25)
            else:
                user_level = 'No Knowledge'
                user_score = 0

            # Calculate Gap Score
            gap_score = max(0, req_score - user_score)

            # Categorize Skill Status
            if user_score >= req_score:
                status = 'STRONG'
                strong_count += 1
            elif user_score > 0:
                status = 'PARTIAL'
                partial_count += 1
            else:
                if importance == 'Low':
                    status = 'LOW_PRIORITY'
                else:
                    status = 'MISSING'
                missing_count += 1

            # Priority Level Engine
            priority = self._calculate_skill_priority(importance, status, gap_score, difficulty)

            # Topic-Level Gap Decomposition
            known_topics, remaining_topics, remaining_hours = self._decompose_topics(
                canonical_req_name,
                all_topics,
                user_score,
                req_score,
                est_total_hours,
                topic_evaluations
            )

            total_remaining_hours += remaining_hours

            # Weighted Career Readiness contributions
            effective_user_score = min(user_score, req_score)
            # If user checked specific topics, calculate topic-based effective score
            if canonical_req_name in topic_evaluations and all_topics:
                topic_ratio = len(known_topics) / max(1, len(all_topics))
                effective_user_score = int(topic_ratio * req_score)

            total_weighted_user_score += (effective_user_score * importance_weight)
            total_weighted_req_score += (req_score * importance_weight)

            item = {
                'skill_name': req_skill_name,
                'normalized_skill_name': canonical_req_name,
                'category': category,
                'importance': importance,
                'importance_weight': importance_weight,
                'required_level': req_level,
                'required_score': req_score,
                'user_level': user_level,
                'user_score': user_score,
                'gap_score': gap_score,
                'status': status,
                'priority': priority,
                'difficulty': difficulty,
                'estimated_hours': est_total_hours,
                'remaining_hours': remaining_hours,
                'all_topics': all_topics,
                'known_topics': known_topics,
                'remaining_topics': remaining_topics
            }
            gap_items.append(item)

        # 6. Overall Career Readiness Score
        if total_weighted_req_score > 0:
            readiness_score = int(round((total_weighted_user_score / total_weighted_req_score) * 100))
            readiness_score = min(100, max(0, readiness_score))
        else:
            readiness_score = 50

        # 7. Duration & Completion Date Calculations
        if total_remaining_hours > 0:
            estimated_weeks = max(1, math.ceil(total_remaining_hours / weekly_hours))
            completion_date = datetime.now(timezone.utc) + timedelta(weeks=estimated_weeks)
            completion_date_str = completion_date.strftime("%B %d, %Y")
        else:
            estimated_weeks = 0
            completion_date_str = "Target Reached!"

        # 8. Sort Gap Items: Priority order (Critical -> High -> Medium -> Low), then remaining hours
        priority_order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
        gap_items.sort(key=lambda x: (
            priority_order.get(x['priority'], 9),
            -x['gap_score'],
            -x['remaining_hours']
        ))

        # 9. Generate Top Recommendations
        recommendations = self._generate_recommendations(gap_items, target_role)

        result = {
            'target_role': market_data['target_role'],
            'normalized_role': market_data['normalized_role'],
            'is_custom_role': market_data['is_custom_role'],
            'market_status': market_data['market_status'],
            'explanation': market_data['explanation'],
            'readiness_score': readiness_score,
            'total_learning_hours': total_remaining_hours,
            'estimated_weeks': estimated_weeks,
            'completion_date': completion_date_str,
            'weekly_hours': weekly_hours,
            'strong_count': strong_count,
            'partial_count': partial_count,
            'missing_count': missing_count,
            'gap_items': gap_items,
            'recommendations': recommendations,
            'topic_evaluations': topic_evaluations
        }

        return result

    def _calculate_skill_priority(self, importance, status, gap_score, difficulty):
        """Calculates Priority level based on market importance, gap severity, and difficulty."""
        if status == 'STRONG':
            return 'Low'
        if importance == 'Critical':
            if status == 'MISSING' or gap_score >= 50:
                return 'Critical'
            return 'High'
        if importance == 'High':
            if status == 'MISSING':
                return 'High'
            return 'High' if gap_score >= 25 else 'Medium'
        if importance == 'Medium':
            return 'Medium'
        return 'Low'

    def _decompose_topics(self, skill_name, all_topics, user_score, req_score, est_total_hours, topic_evaluations):
        """
        Decomposes skill topics into known vs remaining topics and calculates remaining hours.
        Supports custom user topic evaluation overrides.
        """
        if not all_topics:
            # Generate synthetic topics if empty
            all_topics = [
                {'name': f'{skill_name} Fundamentals', 'difficulty': 'Easy', 'hours': int(est_total_hours * 0.3)},
                {'name': f'{skill_name} Core Concepts & Implementation', 'difficulty': 'Moderate', 'hours': int(est_total_hours * 0.4)},
                {'name': f'{skill_name} Advanced Techniques & Best Practices', 'difficulty': 'Difficult', 'hours': int(est_total_hours * 0.3)}
            ]

        # Check if user submitted explicit topic evaluations
        user_checked_names = topic_evaluations.get(skill_name)
        if user_checked_names is not None:
            known_topics = []
            remaining_topics = []
            for t in all_topics:
                t_name = t.get('name') if isinstance(t, dict) else str(t)
                if t_name in user_checked_names:
                    known_topics.append(t)
                else:
                    remaining_topics.append(t)

            remaining_hours = sum(
                (t.get('hours', 6) if isinstance(t, dict) else 6) for t in remaining_topics
            )
            return known_topics, remaining_topics, remaining_hours

        # Infer known topics from user proficiency score
        total_topic_count = len(all_topics)
        if user_score == 0:
            known_count = 0
        elif user_score >= req_score:
            known_count = total_topic_count
        else:
            ratio = user_score / max(1, req_score)
            known_count = min(total_topic_count - 1, max(1, round(ratio * total_topic_count)))

        known_topics = all_topics[:known_count]
        remaining_topics = all_topics[known_count:]

        if user_score >= req_score:
            remaining_hours = 0
        else:
            remaining_hours = sum(
                (t.get('hours', 6) if isinstance(t, dict) else 6) for t in remaining_topics
            )
            # Ensure remaining hours scale with score gap
            if est_total_hours and remaining_hours == 0 and req_score > user_score:
                remaining_hours = int(est_total_hours * ((req_score - user_score) / req_score))

        return known_topics, remaining_topics, remaining_hours

    def _generate_recommendations(self, gap_items, target_role):
        """Generates top 5 prioritized, actionable learning next steps with rationale."""
        recommendations = []
        
        # Filter for skills that need learning
        actionable_items = [i for i in gap_items if i['status'] in ('MISSING', 'PARTIAL', 'LOW_PRIORITY') and i['remaining_topics']]

        for item in actionable_items[:5]:
            skill = item['skill_name']
            rem_topics = item['remaining_topics']
            top_topic = rem_topics[0].get('name') if isinstance(rem_topics[0], dict) else str(rem_topics[0])
            status = item['status']
            priority = item['priority']

            if status == 'MISSING':
                action_text = f"Start with {skill} — Learn '{top_topic}'"
                reason = f"{skill} is a {item['importance']} requirement for {target_role}. Building fundamentals here closes your largest career gap."
            else:
                action_text = f"Level up in {skill} — Master '{top_topic}'"
                reason = f"You have foundational {skill} knowledge. Advancing to {item['required_level']} level unlocks full job readiness."

            recommendations.append({
                'action': action_text,
                'skill': skill,
                'topic': top_topic,
                'priority': priority,
                'estimated_hours': item['remaining_hours'],
                'reason': reason
            })

        # If user is already strong in everything, provide capstone project recommendation
        if not recommendations:
            recommendations.append({
                'action': f"Build an End-to-End {target_role} Capstone Project",
                'skill': "Portfolio Project",
                'topic': "Production Project Architecture",
                'priority': "High",
                'estimated_hours': 30,
                'reason': f"You meet all required skill benchmarks for {target_role}. Demonstrating end-to-end implementation in a portfolio project is the best next step."
            })

        return recommendations

    def save_analysis_to_db(self, user_id, analysis_result):
        """Persists or updates SkillGapAnalysis and SkillGapItem records in SQLite."""
        if not user_id:
            return None

        # Check for existing analysis record
        existing = SkillGapAnalysis.query.filter_by(user_id=user_id).order_by(SkillGapAnalysis.id.desc()).first()
        
        if not existing:
            existing = SkillGapAnalysis(user_id=user_id)
            db.session.add(existing)

        existing.target_role = analysis_result['target_role']
        existing.normalized_role = analysis_result['normalized_role']
        existing.is_custom_role = analysis_result['is_custom_role']
        existing.market_status = analysis_result['market_status']
        existing.readiness_score = analysis_result['readiness_score']
        existing.total_learning_hours = analysis_result['total_learning_hours']
        existing.estimated_weeks = analysis_result['estimated_weeks']
        existing.completion_date_str = analysis_result['completion_date']
        existing.strong_count = analysis_result['strong_count']
        existing.partial_count = analysis_result['partial_count']
        existing.missing_count = analysis_result['missing_count']
        existing.explanation = analysis_result['explanation']
        existing.set_topic_evaluations(analysis_result.get('topic_evaluations', {}))
        existing.set_recommendations(analysis_result.get('recommendations', []))
        existing.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        # Update items
        SkillGapItem.query.filter_by(analysis_id=existing.id).delete()

        for item_data in analysis_result.get('gap_items', []):
            item = SkillGapItem(
                analysis_id=existing.id,
                skill_name=item_data['skill_name'],
                normalized_skill_name=item_data['normalized_skill_name'],
                category=item_data['category'],
                importance=item_data['importance'],
                importance_weight=item_data['importance_weight'],
                required_level=item_data['required_level'],
                required_score=item_data['required_score'],
                user_level=item_data['user_level'],
                user_score=item_data['user_score'],
                gap_score=item_data['gap_score'],
                status=item_data['status'],
                priority=item_data['priority'],
                difficulty=item_data['difficulty'],
                estimated_hours=item_data['estimated_hours'],
                remaining_hours=item_data['remaining_hours']
            )
            item.set_all_topics(item_data.get('all_topics', []))
            item.set_known_topics(item_data.get('known_topics', []))
            item.set_remaining_topics(item_data.get('remaining_topics', []))
            db.session.add(item)

        db.session.commit()
        return existing


# Global service singleton instance
skill_gap_service = SkillGapService()
