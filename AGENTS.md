# Repository Guidelines

## Project Structure & Module Organization
- `batch.py`：主入口，将 GEM5/XS 的统计日志解析为 CSV（见 `batch.py -h`）。
- `utils/`：统计项（targets）定义与工具（重点看 `utils/target_stats.py`，基于正则匹配）。
- `simpoint_cpt/`：SimPoint 加权与 SPEC score 计算（核心脚本 `compute_weighted.py`）。
- `topdown/`：Topdown 分析与绘图脚本。
- `example-scripts/`：常用封装脚本（建议从这里开始用）。
- `results/`、`figure/`、`outputs/` 等为生成物目录（大多数 `*.csv`/`*.png` 已在 gitignore 中忽略）。
- `core_pipeline/`：实验性/可选流水线，目前不是主工作流。

## Build, Test, and Development Commands
- 安装依赖：`python3 -m pip install -r requirements.txt`
- 查看参数：`python3 batch.py -h`
- 常用流程（GEM5 topdown + 加权算分）：
  - 按 tag 解析：`bash example-scripts/gem5-topdown-tag.sh tage_noAlt`
  - 直接传结果目录：`bash example-scripts/gem5-topdown-tag.sh /path/to/results/tag`
- 手动抽取示例：`python3 batch.py -s /path/to/results --cache --branch -o results/run.csv`
- 加权/算分：`python3 simpoint_cpt/compute_weighted.py -r results/run.csv -j simpoint_cpt/resources/<cluster>.json -o results/run-weighted.csv`

## Coding Style & Naming Conventions
- Python：4 空格缩进；函数/变量用 `snake_case`，命名清晰直白。
- 脚本尽量保持可直接运行：`python3 <file>.py`；避免引入过重的新依赖。
- 新增统计项时：优先扩展 `utils/target_stats.py` 的 target group，并在 `README.md` 里补充新 group 名称/用途。

## Testing Guidelines
- 当前仓库没有稳定、完善的测试体系。新增/重构关键逻辑时，建议在 `tests/` 下补充小而准的 `pytest` 测试，并确保可用 `python3 -m pytest` 运行。

## Commit & Pull Request Guidelines
- Commit 标题通常用简单动词开头（如 `add …`、`fix …`、`update …`、`Refactor …`），短且具体；需要时可附 `(#NN)`。
- PR 建议包含：复现实验的命令、输入目录结构假设、以及一小段可验证输出（例如 CSV 表头或关键指标 diff）。

## Data & Environment Notes
- 部分脚本依赖环境变量/配置（例如双核解析用 `XS_CORE_ID`）；相关改动请在 PR 描述里明确说明。
