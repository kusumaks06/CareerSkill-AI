import json
import plotly
import plotly.graph_objects as go

def generate_readiness_gauge(readiness_score):
    """Generates a sleek dark-mode Gauge Chart for Career Readiness."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=readiness_score,
        number={'suffix': "%", 'font': {'size': 44, 'color': '#F8FAFC', 'family': 'Outfit, sans-serif'}},
        title={'text': "Career Readiness", 'font': {'size': 16, 'color': '#94A3B8', 'family': 'Inter, sans-serif'}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': '#334155', 'tickfont': {'color': '#94A3B8'}},
            'bar': {'color': '#6366F1', 'thickness': 0.28},
            'bgcolor': '#1E293B',
            'borderwidth': 1,
            'bordercolor': '#334155',
            'steps': [
                {'range': [0, 40], 'color': 'rgba(239, 68, 68, 0.15)'},
                {'range': [40, 75], 'color': 'rgba(245, 158, 11, 0.15)'},
                {'range': [75, 100], 'color': 'rgba(34, 197, 94, 0.15)'}
            ],
            'threshold': {
                'line': {'color': '#22C55E', 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=30, b=20),
        height=220,
        font=dict(color='#F8FAFC', family='Inter, sans-serif')
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_skill_breakdown_donut(strong_count, partial_count, missing_count):
    """Generates a Donut Chart showing the breakdown of Strong, Partial, and Missing skills."""
    labels = ['Strong (Meets Goal)', 'Partial Gap', 'Missing Skill']
    values = [strong_count, partial_count, missing_count]
    colors = ['#22C55E', '#F59E0B', '#EF4444']

    # Filter out 0 values to keep chart clean
    active_labels = []
    active_values = []
    active_colors = []
    for l, v, c in zip(labels, values, colors):
        if v > 0:
            active_labels.append(l)
            active_values.append(v)
            active_colors.append(c)

    if not active_values:
        active_labels = ['No Skills Required']
        active_values = [1]
        active_colors = ['#334155']

    fig = go.Figure(data=[go.Pie(
        labels=active_labels,
        values=active_values,
        hole=0.6,
        marker=dict(colors=active_colors, line=dict(color='#0F172A', width=2)),
        textinfo='value+percent',
        textfont=dict(size=12, color='#F8FAFC', family='Inter, sans-serif'),
        hoverinfo='label+value'
    )])

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10),
        height=220,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=11, color='#94A3B8')
        )
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_level_comparison_chart(gap_items):
    """Generates a Grouped Bar Chart comparing Required vs Current Skill Level scores."""
    items = gap_items[:8] if len(gap_items) > 8 else gap_items

    skill_names = [i['skill_name'] for i in items]
    user_scores = [i['user_score'] for i in items]
    required_scores = [i['required_score'] for i in items]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=skill_names,
        y=required_scores,
        name='Required Target',
        marker_color='rgba(99, 102, 241, 0.4)',
        marker_line=dict(color='#6366F1', width=1.5)
    ))

    fig.add_trace(go.Bar(
        x=skill_names,
        y=user_scores,
        name='Your Current Level',
        marker_color='#8B5CF6',
        marker_line=dict(color='#A78BFA', width=1.5)
    ))

    fig.update_layout(
        barmode='group',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=30, b=40),
        height=260,
        font=dict(color='#94A3B8', family='Inter, sans-serif'),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color='#F8FAFC')
        ),
        xaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        ),
        yaxis=dict(
            range=[0, 105],
            gridcolor='#1E293B',
            tickvals=[0, 25, 50, 75, 100],
            ticktext=['None', 'Beginner', 'Intermediate', 'Advanced', 'Expert'],
            tickfont=dict(size=10, color='#94A3B8')
        )
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def generate_priority_hours_chart(gap_items):
    """Generates a Horizontal Bar Chart of Estimated Study Hours ranked by Priority."""
    actionable = [i for i in gap_items if i['remaining_hours'] > 0][:7]
    
    if not actionable:
        actionable = gap_items[:5]

    actionable.reverse()

    skill_names = [i['skill_name'] for i in actionable]
    hours = [i['remaining_hours'] for i in actionable]
    priorities = [i['priority'] for i in actionable]

    color_map = {
        'Critical': '#EF4444',
        'High': '#F59E0B',
        'Medium': '#6366F1',
        'Low': '#22C55E'
    }
    bar_colors = [color_map.get(p, '#6366F1') for p in priorities]

    fig = go.Figure(go.Bar(
        x=hours,
        y=skill_names,
        orientation='h',
        marker=dict(
            color=bar_colors,
            line=dict(color='rgba(255, 255, 255, 0.15)', width=1)
        ),
        text=[f"{h}h ({p})" for h, p in zip(hours, priorities)],
        textposition='auto',
        textfont=dict(color='#FFFFFF', size=11)
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=30),
        height=260,
        font=dict(color='#94A3B8', family='Inter, sans-serif'),
        xaxis=dict(
            title="Estimated Hours",
            gridcolor='#1E293B',
            tickfont=dict(color='#94A3B8')
        ),
        yaxis=dict(
            gridcolor='#1E293B',
            tickfont=dict(size=11, color='#F8FAFC')
        )
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
