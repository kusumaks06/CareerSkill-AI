import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
MARKET_TRENDS_FILE = DATA_DIR / 'market_trends.json'


class MarketTrendService:
    """
    Analytics service leveraging Pandas for data transformations,
    aggregations, statistical summaries, and market trend benchmarking.
    """

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or MARKET_TRENDS_FILE
        self._raw_data: Optional[Dict[str, Any]] = None
        self._roles_df: Optional[pd.DataFrame] = None
        self._skills_df: Optional[pd.DataFrame] = None
        self._load_data()

    def _load_data(self):
        """Loads market trends JSON and initializes foundational Pandas DataFrames."""
        if not self.data_path.exists():
            self._raw_data = {"market_overview": {}, "roles": []}
            self._roles_df = pd.DataFrame()
            self._skills_df = pd.DataFrame()
            return

        with open(self.data_path, 'r', encoding='utf-8') as f:
            self._raw_data = json.load(f)

        roles = self._raw_data.get('roles', [])
        
        # Build roles DataFrame
        role_records = []
        skill_records = []

        for r in roles:
            role_id = r.get('id')
            title = r.get('title')
            category = r.get('category')
            demand_index = r.get('demand_index', 80)
            growth_rate = r.get('growth_rate_pct', 15.0)
            active_openings = r.get('active_openings', 10000)

            sal_usd = r.get('salary', {}).get('usd', {})
            sal_inr = r.get('salary', {}).get('inr_lpa', {})

            work_modes = r.get('work_modes', {})

            role_records.append({
                'role_id': role_id,
                'title': title,
                'category': category,
                'demand_index': demand_index,
                'growth_rate_pct': growth_rate,
                'active_openings': active_openings,
                'salary_entry_usd': sal_usd.get('entry', 70000),
                'salary_mid_usd': sal_usd.get('mid', 100000),
                'salary_senior_usd': sal_usd.get('senior', 140000),
                'salary_lead_usd': sal_usd.get('lead', 180000),
                'salary_entry_inr': sal_inr.get('entry', 8.0),
                'salary_mid_inr': sal_inr.get('mid', 16.0),
                'salary_senior_inr': sal_inr.get('senior', 25.0),
                'salary_lead_inr': sal_inr.get('lead', 38.0),
                'remote_pct': work_modes.get('remote', 50),
                'hybrid_pct': work_modes.get('hybrid', 35),
                'onsite_pct': work_modes.get('onsite', 15),
                'tools_list': r.get('top_tools', []),
                'industry_hiring': r.get('industry_hiring', {})
            })

            # Flatten skills for cross-role skill analytics
            for s in r.get('top_skills', []):
                skill_records.append({
                    'role_id': role_id,
                    'role_title': title,
                    'skill_name': s.get('skill'),
                    'category': s.get('category', 'Technical'),
                    'demand_pct': s.get('demand_pct', 70),
                    'growth_pct': s.get('growth_pct', 15.0),
                    'salary_boost_pct': s.get('salary_boost_pct', 15.0)
                })

        self._roles_df = pd.DataFrame(role_records)
        self._skills_df = pd.DataFrame(skill_records)

    def get_market_overview(self, currency: str = 'usd') -> Dict[str, Any]:
        """Calculates global summary KPIs using Pandas."""
        if self._roles_df is None or self._roles_df.empty:
            return {
                'total_openings': 0,
                'avg_salary_entry': 0,
                'avg_salary_mid': 0,
                'avg_salary_senior': 0,
                'avg_salary_lead': 0,
                'fastest_growing_role': 'Data Analyst',
                'fastest_growing_role_rate': 20.0,
                'top_demanded_skill': 'Python',
                'avg_remote_pct': 50
            }

        total_openings = int(self._roles_df['active_openings'].sum())
        
        if currency.lower() == 'inr':
            avg_entry = round(float(self._roles_df['salary_entry_inr'].mean()), 1)
            avg_mid = round(float(self._roles_df['salary_mid_inr'].mean()), 1)
            avg_senior = round(float(self._roles_df['salary_senior_inr'].mean()), 1)
            avg_lead = round(float(self._roles_df['salary_lead_inr'].mean()), 1)
            currency_prefix = "₹"
            currency_suffix = " LPA"
        else:
            avg_entry = int(self._roles_df['salary_entry_usd'].mean())
            avg_mid = int(self._roles_df['salary_mid_usd'].mean())
            avg_senior = int(self._roles_df['salary_senior_usd'].mean())
            avg_lead = int(self._roles_df['salary_lead_usd'].mean())
            currency_prefix = "$"
            currency_suffix = ""

        # Fastest growing role
        fastest_role_row = self._roles_df.sort_values(by='growth_rate_pct', ascending=False).iloc[0]
        fastest_role_title = fastest_role_row['title']
        fastest_role_rate = fastest_role_row['growth_rate_pct']

        # Most in-demand skill across all roles
        top_skill = "Python"
        if not self._skills_df.empty:
            top_skill_series = self._skills_df.groupby('skill_name')['demand_pct'].mean().sort_values(ascending=False)
            if not top_skill_series.empty:
                top_skill = top_skill_series.index[0]

        avg_remote = round(float(self._roles_df['remote_pct'].mean()), 1)

        raw_overview = self._raw_data.get('market_overview', {})

        return {
            'total_openings': total_openings,
            'total_openings_formatted': f"{total_openings:,}",
            'avg_salary_entry': avg_entry,
            'avg_salary_mid': avg_mid,
            'avg_salary_senior': avg_senior,
            'avg_salary_lead': avg_lead,
            'currency_prefix': currency_prefix,
            'currency_suffix': currency_suffix,
            'fastest_growing_role': fastest_role_title,
            'fastest_growing_role_rate': fastest_role_rate,
            'fastest_growing_skill': raw_overview.get('fastest_growing_skill', 'Generative AI & LLMs'),
            'fastest_growing_skill_rate': raw_overview.get('fastest_growth_rate_pct', 46.8),
            'top_demanded_skill': top_skill,
            'top_hiring_sector': raw_overview.get('top_hiring_sector', 'Tech & Cloud Services'),
            'top_hiring_sector_share': raw_overview.get('top_hiring_sector_share_pct', 36.5),
            'avg_remote_pct': avg_remote
        }

    def get_all_roles_list(self) -> List[Dict[str, str]]:
        """Returns sorted list of available role options for dropdown select."""
        if self._roles_df is None or self._roles_df.empty:
            return []
        
        return [
            {'id': row['role_id'], 'title': row['title'], 'category': row['category']}
            for _, row in self._roles_df.sort_values(by='title').iterrows()
        ]

    def get_role_data(self, role_query: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves structured role analytics for a specific role or canonical match."""
        if not role_query or role_query.lower() in ['all', '']:
            return None

        clean_query = role_query.strip().lower().replace('-', '_').replace(' ', '_')
        
        roles = self._raw_data.get('roles', [])
        for r in roles:
            if r['id'].lower() == clean_query or r['title'].lower() == role_query.strip().lower():
                return r
            if clean_query in r['id'].lower() or r['id'].lower() in clean_query:
                return r

        return None

    def get_salary_benchmark_df(self, currency: str = 'usd', role_id: Optional[str] = None) -> pd.DataFrame:
        """Returns salary benchmarks across seniority levels filtered or unfiltered."""
        df = self._roles_df.copy()
        if role_id and role_id.lower() != 'all':
            clean_id = role_id.strip().lower().replace('-', '_').replace(' ', '_')
            df = df[df['role_id'] == clean_id]

        if df.empty:
            df = self._roles_df.copy()

        if currency.lower() == 'inr':
            return df[['title', 'salary_entry_inr', 'salary_mid_inr', 'salary_senior_inr', 'salary_lead_inr']].rename(
                columns={
                    'salary_entry_inr': 'Entry Level',
                    'salary_mid_inr': 'Mid Level',
                    'salary_senior_inr': 'Senior Level',
                    'salary_lead_inr': 'Lead / Principal'
                }
            )
        else:
            return df[['title', 'salary_entry_usd', 'salary_mid_usd', 'salary_senior_usd', 'salary_lead_usd']].rename(
                columns={
                    'salary_entry_usd': 'Entry Level',
                    'salary_mid_usd': 'Mid Level',
                    'salary_senior_usd': 'Senior Level',
                    'salary_lead_usd': 'Lead / Principal'
                }
            )

    def get_skills_demand_df(self, role_id: Optional[str] = None) -> pd.DataFrame:
        """Returns top skills by demand and growth rate."""
        if self._skills_df is None or self._skills_df.empty:
            return pd.DataFrame()

        df = self._skills_df.copy()
        if role_id and role_id.lower() != 'all':
            clean_id = role_id.strip().lower().replace('-', '_').replace(' ', '_')
            df = df[df['role_id'] == clean_id]
            return df.sort_values(by='demand_pct', ascending=False)
        else:
            # Aggregate across all roles
            agg_df = df.groupby(['skill_name', 'category']).agg({
                'demand_pct': 'mean',
                'growth_pct': 'mean',
                'salary_boost_pct': 'mean'
            }).reset_index()
            return agg_df.sort_values(by='demand_pct', ascending=False).head(12)

    def get_industry_hiring_distribution(self, role_id: Optional[str] = None) -> Dict[str, float]:
        """Calculates percentage of hiring across industry sectors."""
        roles = self._raw_data.get('roles', [])
        
        if role_id and role_id.lower() != 'all':
            clean_id = role_id.strip().lower().replace('-', '_').replace(' ', '_')
            for r in roles:
                if r['id'] == clean_id:
                    return r.get('industry_hiring', {})

        # Global average across roles
        sector_totals = {}
        for r in roles:
            for sector, pct in r.get('industry_hiring', {}).items():
                sector_totals[sector] = sector_totals.get(sector, 0.0) + pct

        total_weight = sum(sector_totals.values())
        if total_weight > 0:
            return {k: round((v / total_weight) * 100, 1) for k, v in sector_totals.items()}
        
        return {
            "Technology & SaaS": 38.0,
            "Financial Services & Banking": 25.0,
            "Healthcare & BioTech": 16.0,
            "E-Commerce & Retail": 12.0,
            "Other Industry Domains": 9.0
        }

    def get_tools_frequency(self, role_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extracts tool adoption frequencies across roles."""
        roles = self._raw_data.get('roles', [])
        
        if role_id and role_id.lower() != 'all':
            clean_id = role_id.strip().lower().replace('-', '_').replace(' ', '_')
            for r in roles:
                if r['id'] == clean_id:
                    tools = r.get('top_tools', [])
                    return [{'tool': t, 'count': 1, 'pct': 100} for t in tools]

        tool_counts = {}
        total_roles = len(roles) if roles else 1
        for r in roles:
            for t in r.get('top_tools', []):
                tool_counts[t] = tool_counts.get(t, 0) + 1

        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {'tool': tool, 'count': count, 'pct': round((count / total_roles) * 100, 1)}
            for tool, count in sorted_tools[:12]
        ]


# Singleton instance
market_trend_service = MarketTrendService()
