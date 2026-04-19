#!/usr/bin/env python3
"""CC Evolution — 静态 changelog 站点生成器。

读取 changes.yaml + 多 repo git log，生成 site/index.html。
纯 stdlib，无外部依赖。
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def _load_site_header() -> str:
    p = Path(__file__).parent / "site-header.html"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _load_navbar() -> str:
    for p in [Path(__file__).parent / "site-navbar.html",
              Path.home() / "Dev" / "devtools" / "lib" / "templates" / "site-navbar.html"]:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


NAVBAR_HTML = _load_navbar()
SITE_HEADER_HTML = _load_site_header()

# --- 尝试加载 PyYAML，无则用简易解析 ---
try:
    import yaml
    def load_yaml(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
except ImportError:
    yaml = None
    def load_yaml(path):
        """Minimal YAML-like parser for changes.yaml structure."""
        return _parse_yaml_minimal(path)


def _parse_yaml_minimal(path: str) -> dict:
    """Parse the changes.yaml without PyYAML — handles our specific structure."""
    import re

    text = Path(path).read_text(encoding="utf-8")
    # Remove comments
    lines = []
    for line in text.splitlines():
        stripped = line.split(" #")[0] if " #" in line and not line.strip().startswith("#") else line
        if stripped.strip().startswith("#"):
            continue
        lines.append(stripped)
    text = "\n".join(lines)

    result = {}

    # Extract simple top-level keys
    for m in re.finditer(r"^(\w+):\s+(.+)$", text, re.MULTILINE):
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("["):
            result[key] = [v.strip().strip("'\"") for v in val.strip("[]").split(",")]
        else:
            result[key] = val

    # Extract phases
    phases = []
    for m in re.finditer(
        r"-\s+id:\s+(\d+)\s+name:\s+(.+?)\s+description:\s+(.+?)(?=\n\s+-\s+id:|\nchanges:)",
        text, re.DOTALL
    ):
        phases.append({
            "id": int(m.group(1)),
            "name": m.group(2).strip(),
            "description": m.group(3).strip(),
        })
    result["phases"] = phases

    # Extract changes
    changes = []
    changes_section = text.split("changes:")[1] if "changes:" in text else ""
    change_blocks = re.split(r"\n  - id:", changes_section)
    for block in change_blocks:
        block = block.strip()
        if not block:
            continue
        if not block.startswith("id:"):
            block = "id:" + block

        change = {}
        # Simple fields
        for key in ("id", "phase", "title", "status", "repo"):
            m = re.search(rf"{key}:\s+(.+)", block)
            if m:
                val = m.group(1).strip()
                change[key] = int(val) if key in ("id", "phase") else val

        # List fields
        m = re.search(r"files:\s*\n((?:\s+-\s+.+\n?)+)", block)
        if m:
            change["files"] = [
                line.strip().lstrip("- ") for line in m.group(1).splitlines() if line.strip()
            ]

        # Multiline fields (before/after/why)
        for key in ("before", "after", "why"):
            m = re.search(rf"{key}:\s*\|\s*\n((?:\s{{6}}.+\n?)+)", block)
            if m:
                change[key] = "\n".join(
                    line[6:] if len(line) > 6 else line.strip()
                    for line in m.group(1).splitlines()
                ).strip()

        if "id" in change:
            changes.append(change)

    result["changes"] = changes
    return result


def get_git_log(repo_path: str, since: str = "2026-04-15", max_count: int = 50) -> list[dict]:
    """Get recent git commits from a repo."""
    if not Path(repo_path).exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log",
             f"--since={since}", f"--max-count={max_count}",
             "--format=%H|%h|%s|%ai|%an"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append({
                    "hash": parts[0],
                    "short": parts[1],
                    "message": parts[2],
                    "date": parts[3][:16],
                    "author": parts[4],
                })
        return commits
    except Exception:
        return []


def get_repo_path(repo_name: str) -> str:
    """Map repo name to local path."""
    home = str(Path.home())
    return os.path.join(home, "Dev", repo_name)


STATUS_COLORS = {
    "done": "#1a7f37",
    "in_progress": "#bf8700",
    "in-progress": "#bf8700",
    "pending": "#656d76",
}

STATUS_LABELS = {
    "done": "完成",
    "in_progress": "进行中",
    "in-progress": "进行中",
    "pending": "待开始",
}


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_change_card(change: dict, commits: list[dict]) -> str:
    """Render a single change item as an HTML card."""
    status = change.get("status", "pending")
    color = STATUS_COLORS.get(status, "#656d76")
    label = STATUS_LABELS.get(status, status)

    before_html = escape_html(change.get("before", "")).replace("\n", "<br>")
    after_html = escape_html(change.get("after", "")).replace("\n", "<br>")
    why_html = escape_html(change.get("why", ""))

    files_html = ""
    if change.get("files"):
        files_items = "".join(
            f'<code>{escape_html(f)}</code> ' for f in change["files"]
        )
        files_html = f'<div class="files">{files_items}</div>'

    # Show all commits from the same repo
    related_commits = commits[:5]

    commits_html = ""
    if related_commits:
        items = "".join(
            f'<div class="commit"><code>{c["short"]}</code> {escape_html(c["message"])} <span class="date">{c["date"]}</span></div>'
            for c in related_commits[:5]
        )
        commits_html = f'<div class="commits"><div class="commits-title">关联 Commits</div>{items}</div>'

    return f"""
    <div class="card" id="change-{change.get('id', '')}">
      <div class="card-header">
        <span class="change-id">#{change.get('id', '')}</span>
        <span class="change-title">{escape_html(change.get('title', ''))}</span>
        <span class="badge" style="background:{color}">{label}</span>
        <span class="repo-tag">{escape_html(change.get('repo', ''))}</span>
      </div>
      <div class="why">{why_html}</div>
      {files_html}
      <div class="comparison">
        <div class="before">
          <div class="col-title">Before</div>
          <div class="col-content">{before_html}</div>
        </div>
        <div class="after">
          <div class="col-title">After</div>
          <div class="col-content">{after_html}</div>
        </div>
      </div>
      {commits_html}
    </div>
    """


def render_html(data: dict, all_commits: dict[str, list[dict]]) -> str:
    """Render the full HTML page."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group changes by phase
    phases = {p["id"]: p for p in data.get("phases", [])}
    changes_by_phase: dict[int, list[dict]] = {}
    for c in data.get("changes", []):
        pid = c.get("phase", 0)
        changes_by_phase.setdefault(pid, []).append(c)

    # Stats
    total = len(data.get("changes", []))
    done = sum(1 for c in data.get("changes", []) if c.get("status") == "done")
    in_progress = sum(1 for c in data.get("changes", []) if c.get("status") in ("in_progress", "in-progress"))
    total_commits = sum(len(v) for v in all_commits.values())

    # Build phase sections
    phases_html = ""
    for pid in sorted(changes_by_phase.keys()):
        phase = phases.get(pid, {"name": f"Phase {pid}", "description": ""})
        cards = "".join(
            render_change_card(c, all_commits.get(c.get("repo", ""), []))
            for c in changes_by_phase[pid]
        )
        phases_html += f"""
        <div class="phase">
          <div class="phase-header">
            <span class="phase-id">Phase {pid}</span>
            <span class="phase-name">{escape_html(phase['name'])}</span>
          </div>
          <div class="phase-desc">{escape_html(phase.get('description', ''))}</div>
          <div class="cards">{cards}</div>
        </div>
        """

    # Recent commits sidebar
    recent_commits = []
    for repo, commits in all_commits.items():
        for c in commits:
            c["_repo"] = repo
            recent_commits.append(c)
    recent_commits.sort(key=lambda x: x["date"], reverse=True)

    commits_sidebar = ""
    for c in recent_commits[:20]:
        commits_sidebar += f"""
        <div class="sidebar-commit">
          <div class="sidebar-commit-repo">{escape_html(c['_repo'])}</div>
          <code>{c['short']}</code> {escape_html(c['message'][:60])}
          <div class="sidebar-commit-date">{c['date']}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CC Evolution — 自我进化系统变更日志</title>
<style>
  :root {{
    --bg: #f6f8fa;
    --card-bg: #ffffff;
    --border: #d0d7de;
    --text: #1f2328;
    --text-secondary: #656d76;
    --accent: #0969da;
    --before-bg: #fff1f0;
    --after-bg: #f0fff4;
    --code-bg: #eff1f3;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  header {{
    background: linear-gradient(135deg, #0969da 0%, #1a7f37 100%);
    color: white;
    padding: 40px 24px;
    text-align: center;
  }}
  header h1 {{ font-size: 28px; font-weight: 600; }}
  header p {{ opacity: 0.85; margin-top: 8px; font-size: 15px; }}

  .stats {{
    display: flex;
    gap: 16px;
    justify-content: center;
    margin-top: 20px;
    flex-wrap: wrap;
  }}
  .stat {{
    background: rgba(255,255,255,0.15);
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 14px;
  }}
  .stat strong {{ font-size: 20px; display: block; }}

  .layout {{ display: flex; gap: 24px; margin-top: 24px; }}
  .main {{ flex: 1; min-width: 0; }}
  .sidebar {{
    width: 300px;
    flex-shrink: 0;
    position: sticky;
    top: 24px;
    align-self: flex-start;
    max-height: calc(100vh - 48px);
    overflow-y: auto;
  }}

  .phase {{ margin-bottom: 32px; }}
  .phase-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
  }}
  .phase-id {{
    background: var(--accent);
    color: white;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 12px;
  }}
  .phase-name {{ font-size: 18px; font-weight: 600; }}
  .phase-desc {{ color: var(--text-secondary); font-size: 14px; margin-bottom: 12px; }}

  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
  }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }}
  .change-id {{ color: var(--text-secondary); font-size: 13px; font-weight: 600; }}
  .change-title {{ font-size: 16px; font-weight: 600; }}
  .badge {{
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
  }}
  .repo-tag {{
    background: var(--code-bg);
    color: var(--text-secondary);
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: monospace;
  }}

  .why {{
    color: var(--text-secondary);
    font-size: 14px;
    margin-bottom: 10px;
    font-style: italic;
  }}

  .files {{ margin-bottom: 10px; }}
  .files code {{
    background: var(--code-bg);
    font-size: 12px;
    padding: 2px 6px;
    border-radius: 3px;
    margin-right: 4px;
    display: inline-block;
    margin-bottom: 4px;
  }}

  .comparison {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 8px;
  }}
  .before, .after {{
    border-radius: 6px;
    padding: 12px;
    font-size: 13px;
  }}
  .before {{ background: var(--before-bg); }}
  .after {{ background: var(--after-bg); }}
  .col-title {{
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    margin-bottom: 6px;
    color: var(--text-secondary);
  }}
  .col-content {{ line-height: 1.5; }}

  .commits {{ margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px; }}
  .commits-title {{ font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }}
  .commit {{
    font-size: 13px;
    padding: 3px 0;
    color: var(--text-secondary);
  }}
  .commit code {{
    background: var(--code-bg);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
  }}
  .commit .date {{ float: right; font-size: 12px; }}

  .sidebar-section {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
  }}
  .sidebar-section h3 {{
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .sidebar-commit {{
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;
    font-size: 13px;
    line-height: 1.4;
  }}
  .sidebar-commit:last-child {{ border-bottom: none; }}
  .sidebar-commit-repo {{
    font-size: 11px;
    color: var(--accent);
    font-weight: 600;
  }}
  .sidebar-commit-date {{
    font-size: 11px;
    color: var(--text-secondary);
  }}
  .sidebar-commit code {{
    background: var(--code-bg);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11px;
  }}

  footer {{
    text-align: center;
    padding: 24px;
    color: var(--text-secondary);
    font-size: 13px;
  }}

  @media (max-width: 768px) {{
    .layout {{ flex-direction: column; }}
    .sidebar {{ width: 100%; position: static; max-height: none; }}
    .comparison {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
{NAVBAR_HTML}
{SITE_HEADER_HTML}
<header>
  <div class="stats">
    <div class="stat"><strong>{total}</strong>变更项</div>
    <div class="stat"><strong>{done}</strong>已完成</div>
    <div class="stat"><strong>{in_progress}</strong>进行中</div>
    <div class="stat"><strong>{total_commits}</strong>Commits</div>
  </div>
</header>

<div class="container">
  <div class="layout">
    <div class="main">
      {phases_html}
    </div>
    <div class="sidebar">
      <div class="sidebar-section">
        <h3>Recent Commits</h3>
        {commits_sidebar if commits_sidebar else '<div style="color:var(--text-secondary);font-size:13px">暂无 commits</div>'}
      </div>
    </div>
  </div>
</div>

<footer>
  Generated {now} &middot; CC Evolution &middot;
  <a href="https://github.com/tianli/cc-evolution" style="color:var(--accent)">GitHub</a>
</footer>

</body>
</html>"""


def main():
    script_dir = Path(__file__).parent
    yaml_path = script_dir / "changes.yaml"
    site_dir = script_dir / "site"

    if not yaml_path.exists():
        print("Error: changes.yaml not found", file=sys.stderr)
        sys.exit(1)

    # Load data
    data = load_yaml(str(yaml_path))

    # Collect git logs from all repos
    repos = data.get("repos", [])
    all_commits = {}
    for repo in repos:
        repo_path = get_repo_path(repo)
        commits = get_git_log(repo_path)
        if commits:
            all_commits[repo] = commits

    # Generate HTML
    html = render_html(data, all_commits)

    # Write output
    site_dir.mkdir(exist_ok=True)
    output = site_dir / "index.html"
    output.write_text(html, encoding="utf-8")
    print(f"Generated {output} ({len(html)} bytes)")
    print(f"  {len(data.get('changes', []))} changes, {sum(len(v) for v in all_commits.values())} commits")


if __name__ == "__main__":
    main()
