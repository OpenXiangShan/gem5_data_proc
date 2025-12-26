#!/usr/bin/env python3
import pandas as pd
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

class ComparisonHandler(BaseHTTPRequestHandler):
    html_content = ""

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(self.html_content.encode())

    def log_message(self, format, *args):
        pass

def generate_html(file1, file2):
    df1 = pd.read_csv(file1, index_col=0)
    df2 = pd.read_csv(file2, index_col=0)

    common_cols = list(df1.columns.intersection(df2.columns))
    common_rows = df1.index.intersection(df2.index)

    data = []
    for row in common_rows:
        row_data = {'benchmark': row}
        for col in common_cols:
            v1 = pd.to_numeric(df1.loc[row, col], errors='coerce')
            v2 = pd.to_numeric(df2.loc[row, col], errors='coerce')
            if pd.isna(v1) or pd.isna(v2):
                row_data[col] = None
            elif v1 == 0:
                row_data[col] = None
            else:
                pct = ((v2 - v1) / v1) * 100
                row_data[col] = {'pct': float(pct), 'v1': float(v1), 'v2': float(v2)}
        data.append(row_data)

    import json
    data_json = json.dumps(data)
    cols_json = json.dumps(common_cols)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Weighted CSV Comparison</title>
<link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/css/tabulator.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/js/tabulator.min.js"></script>
<style>
body{{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}}
h2{{color:#333}}
#table{{background:white;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.val{{font-size:0.85em;color:#666;display:block}}
</style></head><body>
<h2>Comparison: {file1.split('/')[-1]} vs {file2.split('/')[-1]}</h2>
<div id="table"></div>
<script>
const data = {data_json};
const columns = [
    {{title: "Benchmark", field: "benchmark", frozen: true, headerFilter: "input", width: 150}}
];
{cols_json}.forEach(col => {{
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
new Tabulator("#table", {{
    data: data,
    columns: columns,
    layout: "fitColumns",
    height: "80vh"
}});
</script></body></html>"""
    return html

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python compare_weighted.py <file1.csv> <file2.csv>")
        sys.exit(1)

    ComparisonHandler.html_content = generate_html(sys.argv[1], sys.argv[2])

    for port in range(8000, 8100):
        try:
            server = HTTPServer(('', port), ComparisonHandler)
            print(f"服务器启动: http://localhost:{port}")
            print("按 Ctrl+C 停止服务器")
            server.serve_forever()
            break
        except OSError:
            continue
