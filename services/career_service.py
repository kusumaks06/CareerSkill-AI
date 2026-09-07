import json
import os
import re
from pathlib import Path
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'careers.json'

# Domain-specific skill enrichments for custom/hybrid job titles
DOMAIN_SKILL_MAP = {
    'healthcare': [
        'Healthcare Analytics',
        'Healthcare Data Standards (HL7/FHIR)',
        'Clinical Data Management',
        'Biostatistics',
        'EHR Data Analysis'
    ],
    'medical': [
        'Medical Informatics',
        'Clinical Trial Data Analysis',
        'Healthcare Compliance (HIPAA)'
    ],
    'sports': [
        'Sports Analytics',
        'Athlete Performance Metrics',
        'Spatial Tracking & Computer Vision in Sports',
        'Tactical Data Modeling'
    ],
    'financial': [
        'Financial Modeling',
        'Risk Analysis & Management',
        'Quantitative Portfolio Analysis',
        'Valuation & Forecasting'
    ],
    'finance': [
        'Financial Analysis',
        'Securities & Stock Market Modeling',
        'Accounting Analytics'
    ],
    'marketing': [
        'Marketing Analytics & Attribution',
        'Customer Acquisition Cost (CAC) Modeling',
        'Google Analytics 4',
        'Cohort & Funnel Analysis'
    ],
    'product': [
        'Product Strategy & Roadmap Planning',
        'User Behavioral Analytics',
        'A/B Experimentation',
        'Feature Adoption Tracking'
    ],
    'vision': [
        'Computer Vision (OpenCV/YOLO)',
        'Image Processing & Segmentation',
        'Convolutional Neural Networks (CNNs)'
    ],
    'nlp': [
        'Natural Language Processing (NLP)',
        'Hugging Face Transformers',
        'Text Embeddings & Vector Search',
        'Large Language Models (LLMs)'
    ],
    'cyber': [
        'Threat Intelligence',
        'Security Information & Event Management (SIEM)',
        'Network Packet Inspection',
        'Vulnerability Assessment'
    ],
    'security': [
        'Cybersecurity Controls & Compliance',
        'Identity & Access Management (IAM)'
    ],
    'cloud': [
        'AWS / Azure Cloud Architecture',
        'Infrastructure as Code (Terraform)',
        'Docker & Kubernetes Containerization'
    ],
    'bioinformatics': [
        'Genomics Data Analysis',
        'Biopython',
        'Sequence Alignment Algorithms'
    ],
    'game': [
        'Game Telemetry Analytics',
        'Player Retention & Monetization Modeling'
    ]
}


class CareerService:
    """Intelligent Career Matching and Market Requirement Synthesizer."""

    def __init__(self, data_path=None):
        self.data_path = data_path or DATA_FILE
        self.careers = self._load_careers()
        self._initialize_vectorizer()

    def _load_careers(self):
        """Loads benchmark careers from JSON file."""
        if not os.path.exists(self.data_path):
            return []
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading careers dataset: {e}")
            return []

    def _initialize_vectorizer(self):
        """Builds TF-IDF matrix over career descriptions, titles, and keywords."""
        if not self.careers:
            self.vectorizer = None
            self.tfidf_matrix = None
            return

        corpus = []
        for c in self.careers:
            # Combine title, keywords, category, and skills into an information-rich document
            doc = (
                f"{c.get('title', '')} {c.get('normalized_title', '')} "
                f"{c.get('category', '')} {c.get('description', '')} "
                f"{' '.join(c.get('domain_keywords', []))} "
                f"{' '.join(c.get('core_skills', []))} "
                f"{' '.join(c.get('tools', []))}"
            )
            corpus.append(doc)

        self.vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    @staticmethod
    def normalize_role(role_text):
        """
        Normalizes role string:
        - Trims whitespace
        - Collapses internal spaces
        - Preserves clean display casing and generates lowercase normalized string.
        """
        if not role_text:
            return "", ""
        
        # Clean display title
        display_title = re.sub(r'\s+', ' ', role_text.strip())
        
        # Lowercase normalized title (remove non-alphanumeric except spaces)
        normalized_title = display_title.lower()
        normalized_title = re.sub(r'[^a-z0-9\s]', '', normalized_title)
        normalized_title = re.sub(r'\s+', ' ', normalized_title).strip()
        
        return display_title, normalized_title

    def analyze_career_role(self, input_role):
        """
        Analyzes any career role entered by the user:
        1. Validates input
        2. Checks for exact benchmark match
        3. If not exact, runs NLP & TF-IDF similarity to find closest related roles
        4. Synthesizes core skills + domain specific skills
        5. Calculates confidence score and generates transparent explanation.
        """
        display_title, normalized_title = self.normalize_role(input_role)

        if not display_title or not normalized_title:
            return {
                'success': False,
                'error': 'Please enter the career or job role you want to pursue.'
            }

        # ---------------------------------------------------------
        # 1. Exact Match Search
        # ---------------------------------------------------------
        for career in self.careers:
            if career.get('normalized_title') == normalized_title:
                return {
                    'success': True,
                    'target_role': display_title,
                    'normalized_role': normalized_title,
                    'is_custom_role': False,
                    'confidence_score': 100,
                    'market_status': 'Verified Industry Benchmark',
                    'explanation': f"Exact match found in industry market database for '{career['title']}'. Requirements reflect verified industry standards.",
                    'matched_skills': career.get('core_skills', []),
                    'secondary_skills': career.get('secondary_skills', []),
                    'tools': career.get('tools', []),
                    'related_roles': [career['title']],
                    'category': career.get('category', 'Technology')
                }

        # ---------------------------------------------------------
        # 2. NLP & Fuzzy Similarity Matching for Custom Roles
        # ---------------------------------------------------------
        similarity_scores = self._calculate_similarities(display_title, normalized_title)

        if not similarity_scores:
            # Fallback if corpus is empty
            fallback_skills = ['Problem Solving', 'Data Analysis', 'Python', 'SQL', 'Critical Thinking']
            return {
                'success': True,
                'target_role': display_title,
                'normalized_role': normalized_title,
                'is_custom_role': True,
                'confidence_score': 70,
                'market_status': 'Estimated Market Requirements',
                'explanation': f"We couldn't find enough exact market data for '{display_title}'. Synthesized estimated foundational tech skills.",
                'matched_skills': fallback_skills,
                'secondary_skills': ['Git', 'Communication'],
                'tools': ['Python', 'SQL'],
                'related_roles': ['Software Developer', 'Data Analyst'],
                'category': 'Custom Career Pathway'
            }

        # Top 2-3 most related career benchmarks
        top_matches = similarity_scores[:2] if len(similarity_scores) >= 2 else similarity_scores[:1]
        top_roles = [match['career'] for match in top_matches]
        top_role_titles = [r['title'] for r in top_roles]

        # ---------------------------------------------------------
        # 3. Synthesize Skills & Domain Enrichments
        # ---------------------------------------------------------
        synthesized_skills = []
        synthesized_tools = []
        synthesized_secondary = []

        # Extract primary overlapping skills from the most related role
        primary_role = top_roles[0]
        for skill in primary_role.get('core_skills', []):
            if skill not in synthesized_skills:
                synthesized_skills.append(skill)

        for tool in primary_role.get('tools', []):
            if tool not in synthesized_tools:
                synthesized_tools.append(tool)

        # Merge secondary role unique skills if relevant
        if len(top_roles) > 1:
            secondary_role = top_roles[1]
            for skill in secondary_role.get('core_skills', []):
                if skill not in synthesized_skills and len(synthesized_skills) < 8:
                    synthesized_skills.append(skill)

        # Check for domain keywords in the user's custom role
        domain_skills = self._extract_domain_skills(normalized_title)
        for d_skill in domain_skills:
            if d_skill not in synthesized_skills:
                # Add domain skills to the priority list
                synthesized_skills.insert(min(len(synthesized_skills), 3), d_skill)

        # Final pass: preserve order while removing any potential duplicates
        unique_skills = []
        for s in synthesized_skills:
            if s not in unique_skills:
                unique_skills.append(s)
        synthesized_skills = unique_skills


        # ---------------------------------------------------------
        # 4. Compute Confidence Score
        # ---------------------------------------------------------
        # Combine TF-IDF similarity score + domain token overlap
        top_sim = top_matches[0]['score']
        # Scale similarity score to realistic 75%-88% range for hybrid/custom roles
        if top_sim > 0.6:
            confidence = int(80 + (top_sim * 10))
        elif top_sim > 0.3:
            confidence = int(76 + (top_sim * 15))
        else:
            confidence = 72

        if domain_skills:
            confidence = max(confidence, 82)

        confidence = min(max(confidence, 65), 92)

        # ---------------------------------------------------------
        # 5. Generate Transparent Explanation
        # ---------------------------------------------------------
        if len(top_role_titles) >= 2:
            roles_formatted = f"'{top_role_titles[0]}' and '{top_role_titles[1]}'"
        else:
            roles_formatted = f"'{top_role_titles[0]}'"

        explanation = (
            f"We couldn't find enough exact market data for '{display_title}'. "
            f"We found related roles such as {roles_formatted} and used their common skills as a starting point."
        )

        return {
            'success': True,
            'target_role': display_title,
            'normalized_role': normalized_title,
            'is_custom_role': True,
            'confidence_score': confidence,
            'market_status': 'Estimated Market Requirements',
            'explanation': explanation,
            'matched_skills': synthesized_skills[:9],
            'secondary_skills': synthesized_secondary,
            'tools': synthesized_tools[:6],
            'related_roles': top_role_titles,
            'category': primary_role.get('category', 'Emerging Role')
        }

    def _calculate_similarities(self, display_title, normalized_title):
        """Calculates combined TF-IDF and sequence matching scores."""
        scores = []
        user_tokens = set(normalized_title.split())

        # Vectorizer search if available
        tfidf_scores = [0.0] * len(self.careers)
        if self.vectorizer and self.tfidf_matrix is not None:
            try:
                user_vec = self.vectorizer.transform([display_title + " " + normalized_title])
                sims = cosine_similarity(user_vec, self.tfidf_matrix)[0]
                tfidf_scores = list(sims)
            except Exception:
                pass

        for idx, career in enumerate(self.careers):
            career_norm = career.get('normalized_title', '')
            
            # String sequence similarity
            seq_sim = SequenceMatcher(None, normalized_title, career_norm).ratio()
            
            # Token overlap
            career_tokens = set(career_norm.split())
            overlap = len(user_tokens.intersection(career_tokens)) / max(len(user_tokens), 1)
            
            # Keywords overlap
            keyword_overlap = 0
            for kw in career.get('domain_keywords', []):
                if kw in normalized_title or any(ut in kw for ut in user_tokens):
                    keyword_overlap += 0.2

            # Weighted combined score
            tfidf_val = tfidf_scores[idx] if idx < len(tfidf_scores) else 0.0
            combined_score = (tfidf_val * 0.45) + (seq_sim * 0.25) + (overlap * 0.20) + (keyword_overlap * 0.10)

            scores.append({
                'career': career,
                'score': combined_score
            })

        scores.sort(key=lambda x: x['score'], reverse=True)
        return scores

    def _extract_domain_skills(self, normalized_title):
        """Extracts domain-specific skills for known specialized domains."""
        extracted = []
        for domain_key, skills in DOMAIN_SKILL_MAP.items():
            if domain_key in normalized_title:
                for s in skills:
                    if s not in extracted:
                        extracted.append(s)
        return extracted


# Global singleton instance for easy import
career_service = CareerService()
