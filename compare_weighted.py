#!/usr/bin/env python3

import argparse
from datetime import datetime
import json
import socket
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pandas as pd


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


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
                # Preserve YAML key order used by utils.targets_yaml.
                for sec in (
                    "gem5",
                    "gem5_regex",
                    "xs",
                    "derived_gem5",
                    "derived_xs",
                    "derived",
                ):
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
    health = {}

    def do_GET(self):
        self._serve_request(write_body=True)

    def do_HEAD(self):
        self._serve_request(write_body=False)

    def _serve_request(self, write_body: bool):
        started = time.monotonic()
        path = self.path.split("?", 1)[0]
        method = self.command
        status = 200
        body = b""
        content_type = "text/html; charset=utf-8"
        error = ""

        try:
            if path in {"/", "/index.html"}:
                body = self.html_content.encode()
            elif path == "/healthz":
                content_type = "application/json; charset=utf-8"
                payload = dict(self.health)
                payload["status"] = "ok"
                payload["uptime_sec"] = round(time.monotonic() - payload.get("started_at", time.monotonic()), 3)
                body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
            elif path == "/favicon.ico":
                status = 204
            else:
                status = 404
                content_type = "text/plain; charset=utf-8"
                body = b"not found\n"

            self.send_response(status)
            if status != 204:
                self.send_header("Content-type", content_type)
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body and write_body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError) as exc:
            error = f" client_disconnected={type(exc).__name__}"
        except Exception as exc:
            error = f" error={type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000
            host, port = self.client_address[:2]
            ua = self.headers.get("User-Agent", "-")
            log(
                f"{method} {path} from {host}:{port} status={status} bytes={len(body)} "
                f"elapsed_ms={elapsed_ms:.1f} ua={ua!r}{error}"
            )

    def log_message(self, format, *args):
        pass


def read_csv_with_log(path: str, label: str) -> pd.DataFrame:
    started = time.monotonic()
    df = pd.read_csv(path, index_col=0)
    elapsed_ms = (time.monotonic() - started) * 1000
    log(
        f"loaded {label}: path={Path(path)} rows={len(df)} cols={len(df.columns)} "
        f"elapsed_ms={elapsed_ms:.1f}"
    )
    return df


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
    df1 = read_csv_with_log(file1, "file1")
    df2 = read_csv_with_log(file2, "file2")

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
                    pct = 0.0 if v2 == 0 else None
                    row_data[col] = {'pct': pct, 'v1': float(v1), 'v2': float(v2), 'zero_base': True}
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

    log(
        "comparison summary: "
        f"rows={len(all_rows)} cols={len(all_cols)} groups={len(group_to_cols)} "
        f"default_group={picked_default_group!r} "
        f"only_in_file1={len(only_in_file1)} only_in_file2={len(only_in_file2)} "
        f"cols_only_in_file1={len(cols_only_in_file1)} cols_only_in_file2={len(cols_only_in_file2)}"
    )

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
#groupBox{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:1100px}}
#groupBox label{{display:flex;gap:6px;align-items:center}}
.col-hide{{margin-left:6px;color:#999;cursor:pointer}}
.col-hide:hover{{color:#222}}
#table{{background:white;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.val{{font-size:0.85em;color:#666;display:block}}
</style></head><body>
<h2>Comparison: {file1.split('/')[-1]} vs {file2.split('/')[-1]}</h2>
<div id="controls">
  <div id="groupBox"></div>
  <label><input type="checkbox" id="showMeta">show meta</label>
  <label><input type="checkbox" id="onlyChanged">only changed</label>
  <label>Columns
    <input type="text" id="colPattern" placeholder="substring (case-sensitive)">
  </label>
  <button id="hideMatched" type="button">hide matched</button>
  <button id="showMatched" type="button">show matched</button>
  <button id="resetHidden" type="button">reset hidden</button>
  <button id="exportCsv" type="button">export csv</button>
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
            if (val.zero_base && typeof pct !== "number") {{
                return `<div style="background:#fff8e1;padding:4px"><b>N/A</b>
                <span class="val">${{val.v1.toFixed(2)}} → ${{val.v2.toFixed(2)}}</span></div>`;
            }}
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

// Click the small "x" in a column header to hide that column.
document.getElementById("table").addEventListener("click", (e) => {{
  const t = e.target;
  if (t && t.classList && t.classList.contains("col-hide")) {{
    const col = t.getAttribute("data-col");
    if (col) {{
      hiddenByUser.add(col);
      updateVisibility();
    }}
    e.stopPropagation();
  }}
}});

function updateVisibility() {{
  const selected = Array.from(document.querySelectorAll("#groupBox input[data-group]:checked")).map(x => x.getAttribute("data-group"));
  const showMeta = document.getElementById("showMeta").checked;
  const onlyChanged = document.getElementById("onlyChanged").checked;

  let visible = new Set();
  if (selected.includes("all") || selected.length === 0) {{
    for (const c of allCols) visible.add(c);
  }} else {{
    for (const g of selected) {{
      const cols = groupToCols[g] || [];
      for (const c of cols) visible.add(c);
    }}
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
  const box = document.getElementById("groupBox");
  function addGroupCheckbox(name, checked) {{
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.setAttribute("data-group", name);
    input.checked = !!checked;
    label.appendChild(input);
    const t = document.createTextNode(name);
    label.appendChild(t);
    box.appendChild(label);
    return input;
  }}

  const allCb = addGroupCheckbox("all", false);
  const groupCbs = {{}};
  for (const g of groups) {{
    groupCbs[g] = addGroupCheckbox(g, false);
  }}

  const preferred = (defaultGroup === "all" || groups.includes(defaultGroup)) ? defaultGroup : "all";
  if (preferred === "all") {{
    allCb.checked = true;
  }} else {{
    groupCbs[preferred].checked = true;
  }}

  function normalizeSelection(changed) {{
    if (changed === "all" && allCb.checked) {{
      for (const g of groups) groupCbs[g].checked = false;
    }} else if (changed !== "all" && groupCbs[changed] && groupCbs[changed].checked) {{
      allCb.checked = false;
    }}
    updateVisibility();
  }}

  allCb.addEventListener("change", () => normalizeSelection("all"));
  for (const g of groups) {{
    groupCbs[g].addEventListener("change", () => normalizeSelection(g));
  }}

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

  function csvEscape(s) {{
    const needs = /[\",\\n\\r]/.test(s);
    if (!needs) return s;
    return '\"' + s.replace(/\"/g, '\"\"') + '\"';
  }}

  function fmtCell(v) {{
    if (!v) return "";
    if (v.only === 1) return "only file1 (" + v.v1.toFixed(2) + ")";
    if (v.only === 2) return "only file2 (" + v.v2.toFixed(2) + ")";
    if (v.zero_base && typeof v.pct !== "number") return "N/A (" + v.v1.toFixed(2) + " -> " + v.v2.toFixed(2) + ")";
    if (typeof v.pct !== "number") return "";
    const pct = v.pct;
    const sign = pct >= 0 ? "+" : "";
    return sign + pct.toFixed(2) + "% (" + v.v1.toFixed(2) + " -> " + v.v2.toFixed(2) + ")";
  }}

  function exportCsv() {{
    const cols = [];
    for (const c of table.getColumns()) {{
      if (c.isVisible && c.isVisible()) cols.push(c.getField());
    }}
    const rows = table.getData("active");
    const header = cols.map(csvEscape).join(",") + "\\n";
    let body = "";
    for (const r of rows) {{
      const line = cols.map(f => {{
        const v = r[f];
        if (f === "benchmark") return csvEscape(String(v ?? ""));
        return csvEscape(fmtCell(v));
      }}).join(",");
      body += line + "\\n";
    }}
    const csv = header + body;
    const blob = new Blob([csv], {{type: "text/csv;charset=utf-8"}});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "diff.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }}
  document.getElementById("exportCsv").addEventListener("click", exportCsv);

  updateVisibility();
}}

initControls();
</script></body></html>"""
    return html


def print_access_hint(host: str, port: int) -> None:
    hostname = socket.gethostname()
    print("=" * 72, flush=True)
    print("服务器启动，浏览器打开:", flush=True)
    print(f"http://localhost:{port}", flush=True)
    print("=" * 72, flush=True)
    log(f"server listening: host={host!r} port={port} hostname={hostname}")
    log(f"remote self-check: curl http://127.0.0.1:{port}/healthz")
    if host in {"", "0.0.0.0"}:
        log(f"remote URL if directly reachable: http://{hostname}:{port}")
    log(
        "SSH tunnel hint: "
        f"ssh -L {port}:127.0.0.1:{port} <user>@{hostname} "
        f"then open http://localhost:{port}"
    )


def serve(html: str) -> None:
    host = "127.0.0.1"
    port = 8000
    ComparisonHandler.html_content = html
    ComparisonHandler.health = {
        "started_at": time.monotonic(),
        "html_bytes": len(html.encode()),
        "host": host,
    }

    candidate_ports = range(port, port + 100)
    last_error = None
    for candidate in candidate_ports:
        try:
            server = ThreadingHTTPServer((host, candidate), ComparisonHandler)
        except OSError as exc:
            last_error = exc
            log(f"port unavailable: host={host!r} port={candidate} error={exc}")
            continue

        ComparisonHandler.health["port"] = candidate
        print_access_hint(host, candidate)
        log("press Ctrl+C to stop server")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log("server stopped by Ctrl+C")
        finally:
            server.server_close()
            log("server closed")
        return

    raise SystemExit(f"failed to bind server starting at port {port}: {last_error}")


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

    html_content = generate_html(opt.file1, opt.file2, default_group=opt.default_group)
    log(f"generated html: bytes={len(html_content.encode())}")
    serve(html_content)
