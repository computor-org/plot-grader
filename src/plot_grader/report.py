"""Generate visual HTML reports."""

import base64
from pathlib import Path
from typing import Dict, Any
from jinja2 import Template
import json


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Plot Grader Validation Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 { color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }
        h2 { color: #555; margin-top: 30px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .stat-box {
            background: #f9f9f9;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #4CAF50;
        }
        .stat-box.error { border-left-color: #f44336; }
        .stat-box.warning { border-left-color: #ff9800; }
        .stat-label {
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }
        .tier-dist {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }
        .tier-bar {
            display: flex;
            height: 40px;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }
        .tier-segment {
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 14px;
        }
        .tier1 { background: #4CAF50; }
        .tier2 { background: #2196F3; }
        .tier3 { background: #FF9800; }
        .error { background: #f44336; }
        .submission {
            border: 1px solid #ddd;
            border-radius: 8px;
            margin: 20px 0;
            padding: 20px;
            background: #fafafa;
        }
        .submission.pass { border-left: 4px solid #4CAF50; }
        .submission.fail { border-left: 4px solid #f44336; }
        .submission.false-negative { border-left: 4px solid #ff9800; }
        .submission.false-positive { border-left: 4px solid #9c27b0; }
        .submission-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .submission-name {
            font-size: 18px;
            font-weight: bold;
        }
        .badge {
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .badge.pass { background: #4CAF50; color: white; }
        .badge.fail { background: #f44336; color: white; }
        .badge.false-negative { background: #ff9800; color: white; }
        .badge.false-positive { background: #9c27b0; color: white; }
        .plots {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 15px;
        }
        .plot-box {
            background: white;
            padding: 15px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .plot-box h4 {
            margin: 0 0 10px 0;
            color: #555;
            font-size: 14px;
        }
        .plot-box img {
            max-width: 100%;
            border-radius: 4px;
        }
        .details {
            margin-top: 15px;
            font-size: 14px;
        }
        .details-row {
            display: grid;
            grid-template-columns: 150px 1fr;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        .details-label {
            font-weight: bold;
            color: #666;
        }
        .check-list {
            margin: 10px 0;
            padding-left: 0;
            list-style: none;
        }
        .check-list li {
            padding: 5px 0;
            font-size: 13px;
        }
        .check-pass::before { content: "✓ "; color: #4CAF50; font-weight: bold; }
        .check-fail::before { content: "✗ "; color: #f44336; font-weight: bold; }
        .check-warn::before { content: "⚠ "; color: #ff9800; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Plot Grader Validation Report</h1>
        <p><strong>Reference:</strong> {{ reference_path }}</p>

        <h2>Overall Statistics</h2>
        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Total Submissions</div>
                <div class="stat-value">{{ total_submissions }}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Pass Rate</div>
                <div class="stat-value">{{ "%.1f"|format(pass_rate * 100) }}%</div>
            </div>
            {% if false_negative_rate is not none %}
            <div class="stat-box {% if false_negative_rate > 0 %}error{% endif %}">
                <div class="stat-label">False Negative Rate</div>
                <div class="stat-value">{{ "%.1f"|format(false_negative_rate * 100) }}%</div>
            </div>
            {% endif %}
            {% if false_positive_rate is not none %}
            <div class="stat-box {% if false_positive_rate > 0.001 %}warning{% endif %}">
                <div class="stat-label">False Positive Rate</div>
                <div class="stat-value">{{ "%.1f"|format(false_positive_rate * 100) }}%</div>
            </div>
            {% endif %}
        </div>

        <h2>Tier Distribution</h2>
        <div class="tier-dist">
            <p>How many submissions resolved at each tier:</p>
            <div class="tier-bar">
                {% for tier, count in tier_distribution.items() %}
                <div class="tier-segment {{ tier.lower().replace(' ', '').replace(':', '') }}"
                     style="width: {{ (count / total_submissions * 100)|round(1) }}%">
                    {{ tier }}: {{ count }} ({{ (count / total_submissions * 100)|round(1) }}%)
                </div>
                {% endfor %}
            </div>
        </div>

        <h2>Submission Results</h2>
        {% for submission in submissions %}
        <div class="submission {% if submission.get('expected_pass') != None and submission.expected_pass and not submission.actual_pass %}false-negative
                                {% elif submission.get('expected_pass') != None and not submission.expected_pass and submission.actual_pass %}false-positive
                                {% elif submission.actual_pass %}pass
                                {% else %}fail{% endif %}">
            <div class="submission-header">
                <div class="submission-name">{{ submission.name }}</div>
                <div>
                    {% if submission.get('expected_pass') != None and submission.expected_pass and not submission.actual_pass %}
                    <span class="badge false-negative">FALSE NEGATIVE</span>
                    {% elif submission.get('expected_pass') != None and not submission.expected_pass and submission.actual_pass %}
                    <span class="badge false-positive">FALSE POSITIVE</span>
                    {% elif submission.actual_pass %}
                    <span class="badge pass">PASS</span>
                    {% else %}
                    <span class="badge fail">FAIL</span>
                    {% endif %}
                </div>
            </div>

            <div class="details">
                <div class="details-row">
                    <div class="details-label">Tier:</div>
                    <div>{{ submission.tier }}</div>
                </div>
                <div class="details-row">
                    <div class="details-label">Score:</div>
                    <div>{{ "%.1f"|format(submission.score) }}/100 (confidence: {{ "%.2f"|format(submission.confidence) }})</div>
                </div>
                <div class="details-row">
                    <div class="details-label">Execution Time:</div>
                    <div>{{ "%.1f"|format(submission.execution_time_ms) }} ms</div>
                </div>
            </div>

            {% if submission.images.submission and submission.images.reference %}
            <div class="plots">
                <div class="plot-box">
                    <h4>Reference Solution</h4>
                    <img src="data:image/png;base64,{{ submission.images.reference }}" alt="Reference plot">
                </div>
                <div class="plot-box">
                    <h4>Student Submission</h4>
                    <img src="data:image/png;base64,{{ submission.images.submission }}" alt="Student plot">
                </div>
            </div>
            {% endif %}

            {% if submission.passed_checks %}
            <div class="details">
                <strong>Passed Checks:</strong>
                <ul class="check-list">
                    {% for check in submission.passed_checks[:5] %}
                    <li class="check-pass">{{ check }}</li>
                    {% endfor %}
                    {% if submission.passed_checks|length > 5 %}
                    <li style="color: #999;">... and {{ submission.passed_checks|length - 5 }} more</li>
                    {% endif %}
                </ul>
            </div>
            {% endif %}

            {% if submission.failed_checks %}
            <div class="details">
                <strong>Failed Checks:</strong>
                <ul class="check-list">
                    {% for check in submission.failed_checks %}
                    <li class="check-fail">{{ check }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}

            {% if submission.warnings %}
            <div class="details">
                <strong>Warnings:</strong>
                <ul class="check-list">
                    {% for warning in submission.warnings %}
                    <li class="check-warn">{{ warning }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}

            {% if submission.error_message %}
            <div class="details">
                <strong style="color: #f44336;">Error:</strong>
                <pre style="background: #ffebee; padding: 10px; border-radius: 4px; overflow-x: auto;">{{ submission.error_message }}</pre>
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def generate_html_report(validation_run: Dict[str, Any], output_path: Path):
    """
    Generate visual HTML report from validation run.

    Args:
        validation_run: ValidationRun.to_dict() output
        output_path: Where to save HTML file
    """
    # Convert image bytes to base64 for embedding
    for submission in validation_run['submissions']:
        if submission['images']['reference']:
            submission['images']['reference'] = base64.b64encode(
                submission['images']['reference']
            ).decode('utf-8')
        if submission['images']['submission']:
            submission['images']['submission'] = base64.b64encode(
                submission['images']['submission']
            ).decode('utf-8')

    template = Template(HTML_TEMPLATE)
    html = template.render(
        reference_path=validation_run['reference_path'],
        total_submissions=len(validation_run['submissions']),
        pass_rate=validation_run['pass_rate'],
        false_negative_rate=validation_run.get('false_negative_rate'),
        false_positive_rate=validation_run.get('false_positive_rate'),
        tier_distribution=validation_run['tier_distribution'],
        submissions=validation_run['submissions'],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)

    # Also save JSON for programmatic access
    json_path = output_path.with_suffix('.json')
    json_path.write_text(json.dumps(validation_run, indent=2, default=str))
