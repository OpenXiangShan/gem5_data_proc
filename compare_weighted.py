#!/usr/bin/env python3

import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pandas as pd


def _load_group_columns(repo_root: Path) -> dict:
    """Return {group_name: [col, ...]} from targets/*.yaml (gem5/xs/derived keys)."""
    try:
        import yaml  # type: ignore
    except Exception:
        # Repo ships PyYAML in requirements.txt; keep a soft failure for portability.
        return {}

    target_dirs = [repo_root / "targets", repo_root / "targets" / "local"]
    group_to_cols: dict = {}

    for d in target_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix not in {".yaml", ".yml"}:
                continue
            data = yaml.safe_load(p.read_text()) or {}
            groups = data.get("groups", {}) or {}
            if not isinstance(groups, dict):
                continue
            for gname, gdef in groups.items():
                if not isinstance(gdef, dict):
                    continue
                cols = set()
                for sec in ("gem5", "xs", "derived"):
                    m = gdef.get(sec, {}) or {}
                    if isinstance(m, dict):
                        for k in m.keys():
                            k = str(k).strip()
                            if k:
                                cols.add(k)
                if cols:
                    group_to_cols.setdefault(str(gname), set()).update(cols)

    return {g: sorted(cols) for g, cols in group_to_cols.items()}

class ComparisonHandler(BaseHTTPRequestHandler):
    html_content = ""

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(self.html_content.encode())

    def log_message(self, format, *args):
        pass


def _pick_default_group(group_to_cols: dict, available_cols: list, preferred: str) -> str:
    if preferred and preferred in group_to_cols:
        return preferred
    # Prefer intel_topdown if available, otherwise fall back to the "largest" group.
    if "intel_topdown" in group_to_cols:
        return "intel_topdown"
    if group_to_cols:
        scored = []
        avail = set(available_cols)
        for g, cols in group_to_cols.items():
            scored.append((len([c for c in cols if c in avail]), g))
        scored.sort(reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]
    return "all"


def generate_html(file1, file2, default_group: str = ""):
    df1 = pd.read_csv(file1, index_col=0)
    df2 = pd.read_csv(file2, index_col=0)

    all_cols = list(df1.columns.union(df2.columns, sort=False))
    cols_only_in_file1 = set(df1.columns) - set(df2.columns)
    cols_only_in_file2 = set(df2.columns) - set(df1.columns)
    all_rows = df1.index.union(df2.index, sort=False)
    only_in_file1 = set(df1.index) - set(df2.index)
    only_in_file2 = set(df2.index) - set(df1.index)

    data = []
    for row in all_rows:
        row_data = {'benchmark': row}
        in_f1 = row not in only_in_file2
        in_f2 = row not in only_in_file1
        for col in all_cols:
            col_in_f1 = col not in cols_only_in_file2
            col_in_f2 = col not in cols_only_in_file1
            v1 = pd.to_numeric(df1.loc[row, col], errors='coerce') if (in_f1 and col_in_f1) else None
            v2 = pd.to_numeric(df2.loc[row, col], errors='coerce') if (in_f2 and col_in_f2) else None
            if pd.isna(v1): v1 = None
            if pd.isna(v2): v2 = None
            if v1 is not None and v2 is not None:
                if v1 == 0:
                    row_data[col] = None
                else:
                    pct = ((v2 - v1) / v1) * 100
                    row_data[col] = {'pct': float(pct), 'v1': float(v1), 'v2': float(v2)}
            elif v1 is not None:
                row_data[col] = {'pct': None, 'v1': float(v1), 'v2': None, 'only': 1}
            elif v2 is not None:
                row_data[col] = {'pct': None, 'v1': None, 'v2': float(v2), 'only': 2}
        data.append(row_data)

    repo_root = Path(__file__).resolve().parent
    group_to_cols = _load_group_columns(repo_root)
    # Only expose groups that actually exist in the current CSV(s).
    avail_set = set(all_cols)
    group_to_cols = {
        g: [c for c in cols if c in avail_set]
        for g, cols in group_to_cols.items()
        if any(c in avail_set for c in cols)
    }
    grouped_cols = set()
    for cols in group_to_cols.values():
        grouped_cols.update(cols)
    meta_cols = sorted([c for c in all_cols if c not in grouped_cols])
    picked_default_group = _pick_default_group(group_to_cols, all_cols, default_group)

    data_json = json.dumps(data)
    cols_json = json.dumps(all_cols)
    group_json = json.dumps(group_to_cols)
    groups_json = json.dumps(sorted(group_to_cols.keys()))
    meta_json = json.dumps(meta_cols)
    default_group_json = json.dumps(picked_default_group)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Weighted CSV Comparison</title>
<link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/css/tabulator.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/js/tabulator.min.js"></script>
<style>
body{{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}}
h2{{color:#333}}
#controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:10px 0 14px 0}}
#controls label{{display:flex;gap:6px;align-items:center}}
#controls input[type="text"]{{padding:4px 6px}}
#table{{background:white;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.val{{font-size:0.85em;color:#666;display:block}}
</style></head><body>
<h2>Comparison: {file1.split('/')[-1]} vs {file2.split('/')[-1]}</h2>
<div id="controls">
  <label>Group
    <select id="groupSelect">
      <option value="all">all</option>
    </select>
  </label>
  <label><input type="checkbox" id="showMeta">show meta</label>
  <label><input type="checkbox" id="onlyChanged">only changed</label>
  <label>Columns
    <input type="text" id="colPattern" placeholder="substring (case-sensitive)">
  </label>
  <button id="hideMatched" type="button">hide matched</button>
  <button id="showMatched" type="button">show matched</button>
  <button id="resetHidden" type="button">reset hidden</button>
</div>
<div id="table"></div>
<script>
const data = {data_json};
const allCols = {cols_json};
const groupToCols = {group_json};
const groups = {groups_json};
const metaCols = {meta_json};
const defaultGroup = {default_group_json};

// Columns with any diff (pct != 0) or present-only markers.
function computeChangedCols() {{
  const changed = new Set();
  for (const row of data) {{
    for (const col of allCols) {{
      const v = row[col];
      if (!v) continue;
      if (v.only === 1 || v.only === 2) {{
        changed.add(col);
        continue;
      }}
      if (typeof v.pct === "number" && v.pct !== 0) {{
        changed.add(col);
      }}
    }}
  }}
  return changed;
}}
const changedCols = computeChangedCols();
const hiddenByUser = new Set();

const columns = [
    {{title: "Benchmark", field: "benchmark", frozen: true, headerFilter: "input", width: 150}}
];
allCols.forEach(col => {{
    columns.push({{
        title: col,
        field: col,
        headerFilter: "input",
        sorter: (a, b) => {{
            const aVal = a ? (a.pct || 0) : 0;
            const bVal = b ? (b.pct || 0) : 0;
            return aVal - bVal;
        }},
        formatter: (cell) => {{
            const val = cell.getValue();
            if (!val) return 'N/A';
            if (val.only === 1) {{
                return `<div style="background:#fff3e0;padding:4px"><b>仅file1</b><span class="val">${{val.v1.toFixed(2)}}</span></div>`;
            }}
            if (val.only === 2) {{
                return `<div style="background:#e3f2fd;padding:4px"><b>仅file2</b><span class="val">${{val.v2.toFixed(2)}}</span></div>`;
            }}
            const pct = val.pct;
            const color = pct > 0 ? '#e8f5e9' : pct < 0 ? '#ffebee' : '#fff';
            const barWidth = Math.min(Math.abs(pct) / 100 * 100, 100);
            const barColor = pct > 0 ? '#4CAF50' : '#f44336';
            return `<div style="position:relative;background:${{color}}">
                <div style="position:absolute;left:0;top:0;height:100%;width:${{barWidth}}%;background:${{barColor}};opacity:0.3"></div>
                <div style="position:relative;padding:4px"><b>${{pct >= 0 ? '+' : ''}}${{pct.toFixed(2)}}%</b>
                <span class="val">${{val.v1.toFixed(2)}} → ${{val.v2.toFixed(2)}}</span></div>
            </div>`;
        }}
    }});
}});
const table = new Tabulator("#table", {{
    data: data,
    columns: columns,
    layout: "fitData",
    movableColumns: true,
    height: "80vh"
}});

function updateVisibility() {{
  const selectedGroup = document.getElementById("groupSelect").value;
  const showMeta = document.getElementById("showMeta").checked;
  const onlyChanged = document.getElementById("onlyChanged").checked;

  let visible = new Set();
  if (selectedGroup === "all") {{
    for (const c of allCols) visible.add(c);
  }} else {{
    const cols = groupToCols[selectedGroup] || [];
    for (const c of cols) visible.add(c);
  }}
  if (showMeta) {{
    for (const c of metaCols) visible.add(c);
  }}
  if (onlyChanged) {{
    visible = new Set([...visible].filter(c => changedCols.has(c)));
  }}

  for (const col of allCols) {{
    const shouldShow = visible.has(col) && !hiddenByUser.has(col);
    if (shouldShow) {{
      table.showColumn(col);
    }} else {{
      table.hideColumn(col);
    }}
  }}
}}

function initControls() {{
  const sel = document.getElementById("groupSelect");
  for (const g of groups) {{
    const opt = document.createElement("option");
    opt.value = g;
    opt.textContent = g;
    sel.appendChild(opt);
  }}
  sel.value = (defaultGroup === "all" || groups.includes(defaultGroup)) ? defaultGroup : "all";

  document.getElementById("groupSelect").addEventListener("change", updateVisibility);
  document.getElementById("showMeta").addEventListener("change", updateVisibility);
  document.getElementById("onlyChanged").addEventListener("change", updateVisibility);

  function hideOrShowMatched(mode) {{
    const pat = document.getElementById("colPattern").value || "";
    const matched = pat ? allCols.filter(c => c.includes(pat)) : [];
    if (!matched.length) return;
    for (const c of matched) {{
      if (mode === "hide") hiddenByUser.add(c);
      if (mode === "show") hiddenByUser.delete(c);
    }}
    updateVisibility();
  }}
  document.getElementById("hideMatched").addEventListener("click", () => hideOrShowMatched("hide"));
  document.getElementById("showMatched").addEventListener("click", () => hideOrShowMatched("show"));
  document.getElementById("resetHidden").addEventListener("click", () => {{
    hiddenByUser.clear();
    document.getElementById("colPattern").value = "";
    updateVisibility();
  }});

  updateVisibility();
}}

initControls();
</script></body></html>"""
    return html

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two weighted CSVs in a local web UI")
    parser.add_argument("file1", help="baseline csv (weighted)")
    parser.add_argument("file2", help="new csv (weighted)")
    parser.add_argument(
        "--default-group",
        default="intel_topdown",
        help="default group to display on page load (default: intel_topdown)",
    )
    opt = parser.parse_args()

    ComparisonHandler.html_content = generate_html(opt.file1, opt.file2, default_group=opt.default_group)

    for port in range(8000, 8100):
        try:
            server = HTTPServer(('', port), ComparisonHandler)
            print(f"服务器启动: http://localhost:{port}")
            print("按 Ctrl+C 停止服务器")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\n服务器停止")
            finally:
                server.server_close()
            break
        except OSError:
            continue
