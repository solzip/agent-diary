"""HTML Dashboard generator — creates a static dashboard page from diary data."""

import calendar
import json
import os
import webbrowser
from collections import Counter
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from claude_diary.config import load_config
from claude_diary.lib.stats import parse_daily_file


def generate_dashboard(diary_dir=None, months=3):
    """Generate HTML dashboard from diary data.

    Args:
        diary_dir: Path to diary directory
        months: Number of months to include

    Returns:
        Path to generated index.html
    """
    config = load_config()
    if diary_dir is None:
        diary_dir = os.path.expanduser(config["diary_dir"])

    tz_offset = config.get("timezone_offset", 9)
    local_tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(local_tz)

    # Collect data
    all_projects = Counter()
    all_categories = Counter()
    daily_data = {}  # date_str -> sessions count
    monthly_sessions = Counter()  # "YYYY-MM" -> count
    total_sessions = 0
    total_files_created = 0
    total_files_modified = 0
    hot_files = Counter()

    for m in range(months):
        year = now.year
        month = now.month - m
        while month <= 0:
            month += 12
            year -= 1
        _, days = calendar.monthrange(year, month)

        for day in range(1, days + 1):
            date_str = "%04d-%02d-%02d" % (year, month, day)
            filepath = os.path.join(diary_dir, "%s.md" % date_str)
            stats = parse_daily_file(filepath)

            sessions = stats["sessions"]
            if sessions > 0:
                daily_data[date_str] = sessions
                total_sessions += sessions
                monthly_sessions["%04d-%02d" % (year, month)] += sessions

                for p in stats["projects"]:
                    all_projects[p] += sessions
                for c in stats.get("categories", []):
                    all_categories[c] += 1
                total_files_created += len(stats["files_created"])
                total_files_modified += len(stats["files_modified"])
                for f in stats["files_modified"]:
                    hot_files[f] += 1

    # Generate HTML
    html = _render_html(
        total_sessions=total_sessions,
        total_files_created=total_files_created,
        total_files_modified=total_files_modified,
        projects=all_projects,
        categories=all_categories,
        daily_data=daily_data,
        hot_files=hot_files,
        months=months,
    )

    # Write to dashboard directory
    dashboard_dir = os.path.join(diary_dir, "dashboard")
    Path(dashboard_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(dashboard_dir, "index.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def serve_dashboard(diary_dir=None, port=8787):
    """Start a local HTTP server for the dashboard."""
    config = load_config()
    if diary_dir is None:
        diary_dir = os.path.expanduser(config["diary_dir"])

    dashboard_dir = os.path.join(diary_dir, "dashboard")
    if not os.path.exists(os.path.join(dashboard_dir, "index.html")):
        generate_dashboard(diary_dir)

    import functools
    handler = functools.partial(SimpleHTTPRequestHandler, directory=dashboard_dir)
    server = HTTPServer(("localhost", port), handler)
    print("Dashboard: http://localhost:%d" % port)
    print("Press Ctrl+C to stop.")

    try:
        webbrowser.open("http://localhost:%d" % port)
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def _render_html(total_sessions, total_files_created, total_files_modified,
                 projects, categories, daily_data, hot_files, months):
    """Render the complete HTML dashboard."""

    # Prepare data as JSON (heatmap + hot files still use inline JS)
    heatmap_data = json.dumps(daily_data)
    hot_files_data = json.dumps([
        {"file": f, "count": c} for f, c in hot_files.most_common(10)
    ])

    # Build CSS bar chart HTML for projects
    bar_colors = ['#58a6ff','#3fb950','#d29922','#f85149','#bc8cff',
                  '#79c0ff','#56d364','#e3b341','#ff7b72','#d2a8ff']
    project_items = projects.most_common(10)
    project_max = project_items[0][1] if project_items else 1
    project_bars_html = ""
    for i, (label, value) in enumerate(project_items):
        pct = max(5, int(value / project_max * 100))
        color = bar_colors[i % len(bar_colors)]
        project_bars_html += (
            '<div class="bar-row">'
            '<span class="bar-label">%s</span>'
            '<div class="bar-track"><div class="bar-fill" style="width:%d%%;background:%s"></div></div>'
            '<span class="bar-value">%d</span>'
            '</div>\n' % (_html_escape(label), pct, color, value)
        )
    if not project_items:
        project_bars_html = '<p style="color:#484f58">No data yet</p>'

    # Build CSS bar chart HTML for categories
    cat_items = categories.most_common(10)
    cat_max = cat_items[0][1] if cat_items else 1
    cat_bars_html = ""
    for _i, (label, value) in enumerate(cat_items):
        pct = max(5, int(value / cat_max * 100))
        cat_bars_html += (
            '<div class="bar-row">'
            '<span class="bar-label">%s</span>'
            '<div class="bar-track"><div class="bar-fill" style="width:%d%%;background:#238636"></div></div>'
            '<span class="bar-value">%d</span>'
            '</div>\n' % (_html_escape(label), pct, value)
        )
    if not cat_items:
        cat_bars_html = '<p style="color:#484f58">No data yet</p>'

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Diary Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 24px; }
h1 { color: #58a6ff; margin-bottom: 24px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }
.stat-card .value { font-size: 2em; font-weight: bold; color: #58a6ff; }
.stat-card .label { font-size: 0.9em; color: #8b949e; margin-top: 4px; }
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }
.chart-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
.chart-card h3 { color: #c9d1d9; margin-bottom: 16px; }
.bar-row { display: flex; align-items: center; margin-bottom: 10px; }
.bar-label { min-width: 100px; max-width: 140px; font-size: 0.85em; color: #c9d1d9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 10px; }
.bar-track { flex: 1; height: 18px; background: #21262d; border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%%; border-radius: 4px; transition: width 0.3s; }
.bar-value { min-width: 36px; text-align: right; font-size: 0.85em; color: #8b949e; margin-left: 10px; }
.heatmap { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 32px; }
.heatmap h3 { margin-bottom: 12px; }
.heatmap-grid { display: flex; flex-wrap: wrap; gap: 3px; }
.heatmap-cell { width: 14px; height: 14px; border-radius: 2px; }
.hot-files { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
.hot-files h3 { margin-bottom: 12px; }
.hot-files .file-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 0.9em; }
.hot-files .file-name { flex: 1; font-family: monospace; color: #79c0ff; }
.hot-files .file-bar { height: 8px; background: #238636; border-radius: 4px; margin: 0 12px; }
.hot-files .file-count { color: #8b949e; min-width: 30px; }
footer { text-align: center; color: #484f58; margin-top: 32px; font-size: 0.85em; }
@media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>📊 Claude Diary Dashboard</h1>

<div class="stats-grid">
  <div class="stat-card"><div class="value">%(total_sessions)d</div><div class="label">Total Sessions</div></div>
  <div class="stat-card"><div class="value">%(total_projects)d</div><div class="label">Projects</div></div>
  <div class="stat-card"><div class="value">%(total_files_created)d</div><div class="label">Files Created</div></div>
  <div class="stat-card"><div class="value">%(total_files_modified)d</div><div class="label">Files Modified</div></div>
</div>

<div class="heatmap">
  <h3>📅 Activity Heatmap (%(months)d months)</h3>
  <div class="heatmap-grid" id="heatmap"></div>
</div>

<div class="charts-grid">
  <div class="chart-card">
    <h3>🗂️ Projects</h3>
    %(project_bars)s
  </div>
  <div class="chart-card">
    <h3>🏷️ Categories</h3>
    %(cat_bars)s
  </div>
</div>

<div class="hot-files">
  <h3>🔥 Frequently Modified Files (Top 10)</h3>
  <div id="hotFiles"></div>
</div>

<footer>Generated by claude-diary</footer>

<script>
const heatmapData = %(heatmap_data)s;
const hotFilesData = %(hot_files_data)s;

// Heatmap
(function() {
  const grid = document.getElementById('heatmap');
  const today = new Date();
  const daysBack = %(months)d * 30;
  for (let i = daysBack; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const count = heatmapData[key] || 0;
    const cell = document.createElement('div');
    cell.className = 'heatmap-cell';
    cell.title = key + ': ' + count + ' sessions';
    if (count === 0) cell.style.background = '#161b22';
    else if (count <= 2) cell.style.background = '#0e4429';
    else if (count <= 4) cell.style.background = '#006d32';
    else if (count <= 6) cell.style.background = '#26a641';
    else cell.style.background = '#39d353';
    grid.appendChild(cell);
  }
})();

// Hot files
(function() {
  const container = document.getElementById('hotFiles');
  const maxCount = hotFilesData.length > 0 ? hotFilesData[0].count : 1;
  hotFilesData.forEach(item => {
    const row = document.createElement('div');
    row.className = 'file-row';
    const barWidth = Math.max(10, (item.count / maxCount) * 200);
    const nameSpan = document.createElement('span');
    nameSpan.className = 'file-name';
    nameSpan.textContent = item.file;
    const barDiv = document.createElement('div');
    barDiv.className = 'file-bar';
    barDiv.style.width = barWidth + 'px';
    const countSpan = document.createElement('span');
    countSpan.className = 'file-count';
    countSpan.textContent = item.count;
    row.appendChild(nameSpan);
    row.appendChild(barDiv);
    row.appendChild(countSpan);
    container.appendChild(row);
  });
  if (hotFilesData.length === 0) container.innerHTML = '<p style="color:#484f58">No data yet</p>';
})();
</script>
</body>
</html>""" % {
        "total_sessions": total_sessions,
        "total_projects": len(projects),
        "total_files_created": total_files_created,
        "total_files_modified": total_files_modified,
        "months": months,
        "heatmap_data": heatmap_data,
        "project_bars": project_bars_html,
        "cat_bars": cat_bars_html,
        "hot_files_data": hot_files_data,
    }


def _html_escape(text):
    """Minimal HTML escape for label text."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
