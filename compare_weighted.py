#!/usr/bin/env python3
import html as html_lib
import os
import pandas as pd
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
                gname = str(gname)
                out = group_to_cols.setdefault(gname, [])
                seen = set(out)
                # Preserve YAML key order: gem5 -> xs -> derived.
                for sec in ("gem5", "xs", "derived"):
                    m = gdef.get(sec, {}) or {}
                    if not isinstance(m, dict):
                        continue
                    for k in m.keys():
                        k = str(k).strip()
                        if not k or k in seen:
                            continue
                        out.append(k)
                        seen.add(k)

    return group_to_cols

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

    all_cols_raw = list(df1.columns.union(df2.columns, sort=False))

    repo_root = Path(__file__).resolve().parent
    group_to_cols_raw = _load_group_columns(repo_root)
    # Only expose groups that actually exist in the current CSV(s), preserving group order.
    avail_set = set(all_cols_raw)
    group_to_cols = {}
    for g in group_to_cols_raw.keys():
        cols = [c for c in group_to_cols_raw[g] if c in avail_set]
        if cols:
            group_to_cols[g] = cols

    # Order columns by YAML definition first, then append any remaining columns
    # in their original CSV order.
    yaml_order = []
    seen = set()
    for g in group_to_cols.keys():
        for c in group_to_cols[g]:
            if c not in seen:
                yaml_order.append(c)
                seen.add(c)
    all_cols = yaml_order + [c for c in all_cols_raw if c not in seen]

    grouped_cols = set()
    for cols in group_to_cols.values():
        grouped_cols.update(cols)
    meta_cols = [c for c in all_cols if c not in grouped_cols]
    picked_default_group = _pick_default_group(group_to_cols, all_cols, default_group)

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

    data_json = json.dumps(data)
    cols_json = json.dumps(all_cols)
    group_json = json.dumps(group_to_cols)
    groups_json = json.dumps(list(group_to_cols.keys()))
    meta_json = json.dumps(meta_cols)
    default_group_json = json.dumps(picked_default_group)

    def format_cell(val):
        if not val:
            return '<span class="na">N/A</span>'
        if val.get('only') == 1:
            return f'<span class="only1">only file1</span><br><span class="val">{val["v1"]:.2f}</span>'
        if val.get('only') == 2:
            return f'<span class="only2">only file2</span><br><span class="val">{val["v2"]:.2f}</span>'
        pct = val.get('pct')
        if pct is None:
            return '<span class="na">N/A</span>'
        sign = "+" if pct >= 0 else ""
        return f'<span class="pct">{sign}{pct:.2f}%</span><br><span class="val">{val["v1"]:.2f} → {val["v2"]:.2f}</span>'

    static_rows = []
    for row in data:
        cells = [f'<td class="bench">{html_lib.escape(str(row.get("benchmark", "")))}</td>']
        for col in all_cols:
            cells.append(f'<td>{format_cell(row.get(col))}</td>')
        static_rows.append("<tr>" + "".join(cells) + "</tr>")
    static_table_html = (
        '<div id="static-table-wrapper">'
        '<table id="static-table">'
        '<thead><tr>'
        + ''.join(f'<th>{html_lib.escape(str(h))}</th>' for h in (["Benchmark"] + all_cols))
        + '</tr></thead>'
        '<tbody>'
        + ''.join(static_rows)
        + '</tbody></table></div>'
    )

    tabulator_dir = os.path.join(os.path.dirname(__file__), "assets", "tabulator")
    tabulator_css_path = os.path.join(tabulator_dir, "tabulator.min.css")
    tabulator_js_path = os.path.join(tabulator_dir, "tabulator.min.js")
    tabulator_css = None
    tabulator_js = None
    if os.path.isfile(tabulator_css_path) and os.path.isfile(tabulator_js_path):
        with open(tabulator_css_path, "r", encoding="utf-8") as f:
            tabulator_css = f.read()
        with open(tabulator_js_path, "r", encoding="utf-8") as f:
            tabulator_js = f.read()
    has_tabulator = tabulator_css is not None and tabulator_js is not None
    tabulator_note = ""
    if not has_tabulator:
        tabulator_note = (
            '<div id="static-note">'
            'Tabulator assets not found. Showing static table. '
            'Place assets at assets/tabulator/tabulator.min.{js,css} to enable interactive view.'
            '</div>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Weighted CSV Comparison</title>
<style>
body{{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}}
h2{{color:#333}}
#controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:10px 0 14px 0}}
#controls label{{display:flex;gap:6px;align-items:center}}
#controls input[type="text"]{{padding:4px 6px}}
#groupBox{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:1100px}}
#groupBox label{{display:flex;gap:6px;align-items:center}}
.col-hide{{margin-left:6px;color:#999;cursor:pointer}}
.col-hide:hover{{color:#222}}
#table{{background:white;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.val{{font-size:0.85em;color:#666;display:block}}
#static-note{{margin:8px 0;color:#666;font-size:12px}}
#static-table-wrapper{{max-height:80vh;overflow:auto;background:white;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
#static-table{{border-collapse:collapse;width:100%}}
#static-table th,#static-table td{{border:1px solid #ddd;padding:6px;font-size:12px;vertical-align:top}}
#static-table th{{background:#fafafa;position:sticky;top:0;z-index:1}}
#static-table .bench{{font-weight:bold;white-space:nowrap}}
.na{{color:#999}}
.only1{{color:#ef6c00;font-weight:bold}}
.only2{{color:#1565c0;font-weight:bold}}
.pct{{font-weight:bold}}
</style></head><body>
<h2>Comparison: {file1.split('/')[-1]} vs {file2.split('/')[-1]}</h2>
{tabulator_note}
<div id="table"></div>
{static_table_html}
{"<style>" + tabulator_css + "</style>" if has_tabulator else ""}
{"<script>" + tabulator_js + "</script>" if has_tabulator else ""}
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
        title: col + '<span class="col-hide" data-col="' + col + '" title="hide">x</span>',
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
const tableEl = document.getElementById("table");
const staticEl = document.getElementById("static-table-wrapper");
if (typeof Tabulator === "undefined") {{
    if (tableEl) tableEl.style.display = "none";
}} else {{
    if (staticEl) staticEl.style.display = "none";
    new Tabulator("#table", {{
        data: data,
        columns: columns,
        layout: "fitData",
        movableColumns: true,
        height: "80vh"
    }});
}}
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
