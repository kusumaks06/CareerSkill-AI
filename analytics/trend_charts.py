import json
from typing import Dict, List, Any, Optional
import pandas as pd
import plotly
import plotly.graph_objects as go
import plotly.express as px


DARK_LAYOUT_DEFAULTS = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(color='#94A3B8', family='Inter, sans-serif'),
    margin=dict(l=20, r=20, t=30, b=30),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=11, color='#F8FAFC')
    )
)


def generate_salary_benchmark_chart(salary_df: pd.DataFrame, currency: str = 'usd') -> str:
    """
    Generates a Grouped Bar Chart of Salary Compensation across seniority levels.
    """
    if salary_df.empty:
        fig = go.Figure()
        fig.update_layout(**DARK_LAYOUT_DEFAULTS)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    prefix = "$" if currency.lower() == 'usd' else "₹"
    suffix = "" if currency.lower() == 'usd' else " LPA"

    titles = salary_df['title'].tolist()
    levels = [col for col in ['Entry Level', 'Mid Level', 'Senior Level', 'Lead / Principal'] if col in salary_df.columns]

    color_palette = {
        'Entry Level': 'rgba(56, 189, 248, 0.85)',       # Sky blue
        'Mid Level': 'rgba(99, 102, 241, 0.85)',         # Indigo
        'Senior Level': 'rgba(168, 85, 247, 0.85)',      # Purple
        'Lead / Principal': 'rgba(236, 72, 153, 0.85)'   # Pink
    }

    fig = go.Figure()

    for level in levels:
        values = salary_df[level].tolist()
        formatted_text = [
            f"{prefix}{v:,.0f}{suffix}" if currency.lower() == 'usd' else f"{prefix}{v:.1f}{suffix}"
            for v in values
        ]

        fig.add_trace(go.Bar(
            name=level,
            x=titles,
            y=values,
            marker_color=color_palette.get(level, '#6366F1'),
            text=formatted_text,
            textposition='auto',
            textfont=dict(size=10, color='#FFFFFF', family='Inter, sans-serif'),
            hovertemplate=f"<b>%{{x}}</b><br>{level}: {prefix}%{{y:,.0f}}{suffix}<extra></extra>" if currency.lower() == 'usd' else f"<b>%{{x}}</b><br>{level}: {prefix}%{{y:.1f}}{suffix}<extra></extra>"
        ))

    layout = DARK_LAYOUT_DEFAULTS.copy()
    fig.update_layout(
        **layout,
        barmode='group',
        height=320,
        xaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        ),
        yaxis=dict(
            title=f"Compensation ({prefix}{suffix})",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_skills_growth_bar_chart(skills_df: pd.DataFrame) -> str:
    """
    Generates a Dual Horizontal Bar Chart ranking skills by Demand % and YoY Growth Rate %.
    """
    if skills_df.empty:
        fig = go.Figure()
        fig.update_layout(**DARK_LAYOUT_DEFAULTS)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    df_subset = skills_df.head(10).iloc[::-1]  # Reverse for top-to-bottom display
    skill_names = df_subset['skill_name'].tolist()
    demand_pcts = df_subset['demand_pct'].tolist()
    growth_pcts = df_subset['growth_pct'].tolist()

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name='Job Demand %',
        y=skill_names,
        x=demand_pcts,
        orientation='h',
        marker_color='rgba(99, 102, 241, 0.85)',
        text=[f"{v:.0f}%" for v in demand_pcts],
        textposition='inside',
        textfont=dict(size=11, color='#FFFFFF'),
        hovertemplate="<b>%{y}</b><br>Job Demand: %{x:.1f}%<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        name='YoY Growth %',
        y=skill_names,
        x=growth_pcts,
        orientation='h',
        marker_color='rgba(34, 197, 94, 0.85)',
        text=[f"+{v:.1f}%" for v in growth_pcts],
        textposition='outside',
        textfont=dict(size=11, color='#22C55E'),
        hovertemplate="<b>%{y}</b><br>Projected Growth: +%{x:.1f}%<extra></extra>"
    ))

    layout = DARK_LAYOUT_DEFAULTS.copy()
    fig.update_layout(
        **layout,
        barmode='group',
        height=320,
        xaxis=dict(
            title="Percentage (%)",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        ),
        yaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_industry_hiring_donut(industry_dict: Dict[str, float]) -> str:
    """
    Generates an interactive Donut Chart for Industry Sector Hiring Distribution.
    """
    labels = list(industry_dict.keys())
    values = list(industry_dict.values())

    colors = [
        '#6366F1',  # Indigo
        '#38BDF8',  # Sky
        '#A855F7',  # Purple
        '#22C55E',  # Green
        '#F59E0B',  # Amber
        '#EC4899',  # Pink
        '#14B8A6'   # Teal
    ]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.62,
        marker=dict(colors=colors, line=dict(color='#0F172A', width=2)),
        textinfo='percent',
        textfont=dict(size=12, color='#F8FAFC', family='Inter, sans-serif'),
        hovertemplate="<b>%{label}</b><br>Hiring Share: %{value:.1f}%<extra></extra>"
    )])

    layout = DARK_LAYOUT_DEFAULTS.copy()
    layout.pop('legend', None)
    fig.update_layout(
        **layout,
        height=280,
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05,
            font=dict(size=11, color='#94A3B8')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_skill_roi_scatter_chart(skills_df: pd.DataFrame) -> str:
    """
    Generates a Bubble / Scatter Plot representing Skill Demand (%) vs Salary Boost (ROI %).
    """
    if skills_df.empty:
        fig = go.Figure()
        fig.update_layout(**DARK_LAYOUT_DEFAULTS)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    df_subset = skills_df.head(15)

    category_colors = {
        'AI/ML': '#A855F7',
        'Programming': '#6366F1',
        'Databases': '#38BDF8',
        'DevOps': '#F59E0B',
        'BI Tools': '#EC4899',
        'Analytics': '#22C55E',
        'Security': '#EF4444',
        'Cloud': '#14B8A6',
        'Product': '#F97316'
    }

    fig = go.Figure()

    for category, group in df_subset.groupby('category'):
        color = category_colors.get(category, '#6366F1')
        
        # Calculate marker sizes based on growth_pct
        sizes = [max(12, min(36, float(g) * 0.75)) for g in group['growth_pct']]

        fig.add_trace(go.Scatter(
            name=category,
            x=group['demand_pct'],
            y=group['salary_boost_pct'],
            mode='markers+text',
            text=group['skill_name'],
            textposition="top center",
            textfont=dict(size=10, color='#F8FAFC'),
            marker=dict(
                size=sizes,
                color=color,
                opacity=0.85,
                line=dict(width=1.5, color='#FFFFFF')
            ),
            hovertemplate="<b>%{text}</b><br>Category: " + category + "<br>Demand: %{x:.1f}%<br>Salary Boost: +%{y:.1f}%<extra></extra>"
        ))

    layout = DARK_LAYOUT_DEFAULTS.copy()
    fig.update_layout(
        **layout,
        height=320,
        xaxis=dict(
            title="Market Demand Frequency (%)",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        ),
        yaxis=dict(
            title="Avg Salary Premium (+%)",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_work_mode_chart(role_data: Optional[Dict[str, Any]] = None, overview_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Generates a Horizontal Stacked Bar Chart for Remote vs Hybrid vs On-site Distribution.
    """
    if role_data and 'work_modes' in role_data:
        wm = role_data['work_modes']
        remote = wm.get('remote', 45)
        hybrid = wm.get('hybrid', 40)
        onsite = wm.get('onsite', 15)
        title_label = role_data.get('title', 'Selected Role')
    else:
        remote = 54
        hybrid = 36
        onsite = 10
        title_label = "Overall Industry Average"

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name='Fully Remote',
        y=[title_label],
        x=[remote],
        orientation='h',
        marker_color='#22C55E',
        text=[f"{remote}% Remote"],
        textposition='inside',
        textfont=dict(size=11, color='#FFFFFF')
    ))

    fig.add_trace(go.Bar(
        name='Hybrid',
        y=[title_label],
        x=[hybrid],
        orientation='h',
        marker_color='#6366F1',
        text=[f"{hybrid}% Hybrid"],
        textposition='inside',
        textfont=dict(size=11, color='#FFFFFF')
    ))

    fig.add_trace(go.Bar(
        name='On-site',
        y=[title_label],
        x=[onsite],
        orientation='h',
        marker_color='#94A3B8',
        text=[f"{onsite}% On-site"],
        textposition='inside',
        textfont=dict(size=11, color='#0F172A')
    ))

    layout = DARK_LAYOUT_DEFAULTS.copy()
    fig.update_layout(
        **layout,
        barmode='stack',
        height=140,
        xaxis=dict(
            range=[0, 100],
            title="Work Arrangement (%)",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        ),
        yaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_tools_popularity_chart(tools_list: List[Dict[str, Any]]) -> str:
    """
    Generates a Horizontal Bar Chart for Top Frameworks & Tooling Popularity.
    """
    if not tools_list:
        fig = go.Figure()
        fig.update_layout(**DARK_LAYOUT_DEFAULTS)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    subset = tools_list[:10][::-1]
    tool_names = [item['tool'] for item in subset]
    pcts = [item['pct'] for item in subset]

    fig = go.Figure(go.Bar(
        x=pcts,
        y=tool_names,
        orientation='h',
        marker=dict(
            color='rgba(56, 189, 248, 0.85)',
            line=dict(color='#38BDF8', width=1)
        ),
        text=[f"{p:.0f}% Adoption" for p in pcts],
        textposition='auto',
        textfont=dict(size=10, color='#FFFFFF'),
        hovertemplate="<b>%{y}</b><br>Adoption across roles: %{x:.1f}%<extra></extra>"
    ))

    layout = DARK_LAYOUT_DEFAULTS.copy()
    fig.update_layout(
        **layout,
        height=300,
        xaxis=dict(
            title="Role Adoption Frequency (%)",
            gridcolor='#1E293B',
            tickfont=dict(size=10, color='#94A3B8')
        ),
        yaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        )
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
