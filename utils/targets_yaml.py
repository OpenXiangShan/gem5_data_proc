import os
import os.path as osp
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from utils.target_patterns import gem5_glob_to_stat_regex


def _snake_case(s: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"__+", "_", s)
    return s.strip("_").lower()


def _format_macros(s: str, macros: Dict[str, str]) -> str:
    for k, v in macros.items():
        s = s.replace("{" + k + "}", v)
    return s


def _join_stat(base: str, suffix: str) -> str:
    if not base:
        return suffix
    if suffix.startswith("system."):
        return suffix
    if base.endswith("."):
        return base + suffix
    if suffix.startswith("."):
        return base + suffix
    return base + "." + suffix


@dataclass(frozen=True)
class LoadedYamlTargets:
    groups: List[str]
    gem5_targets: Dict[str, str]
    xs_targets: Dict[str, str]
    derived: Dict[str, str]


def _load_yaml_file(path: str) -> dict:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "PyYAML is required for YAML targets. Install with: "
            "`python3 -m pip install pyyaml`"
        ) from e

    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"invalid targets yaml (expected mapping): {path}")
    return data


def discover_target_files(dirs: Sequence[str]) -> List[str]:
    files: List[str] = []
    for d in dirs:
        if not d:
            continue
        if not osp.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".yaml") or name.endswith(".yml"):
                files.append(osp.join(d, name))
    return files


def list_groups(dirs: Sequence[str]) -> List[str]:
    groups: List[str] = []
    for f in discover_target_files(dirs):
        data = _load_yaml_file(f)
        g = data.get("groups", {})
        if isinstance(g, dict):
            groups.extend(list(g.keys()))
    return sorted(set(groups))


def load_groups(
    dirs: Sequence[str],
    selected_groups: Sequence[str],
) -> LoadedYamlTargets:
    selected = [g.strip() for g in selected_groups if g.strip()]
    if not selected:
        return LoadedYamlTargets(groups=[], gem5_targets={}, xs_targets={}, derived={})

    all_files = discover_target_files(dirs)
    if not all_files:
        raise FileNotFoundError(f"no targets yaml files found under: {', '.join(dirs)}")

    gem5_targets: Dict[str, str] = {}
    xs_targets: Dict[str, str] = {}
    derived: Dict[str, str] = {}
    loaded_groups: List[str] = []

    for f in all_files:
        data = _load_yaml_file(f)

        domain = str(data.get("domain", "")).strip()
        defaults = data.get("defaults", {}) or {}
        if not isinstance(defaults, dict):
            raise ValueError(f"invalid defaults in {f} (expected mapping)")
        macros: Dict[str, str] = {str(k): str(v) for k, v in defaults.items()}

        groups = data.get("groups", {}) or {}
        if not isinstance(groups, dict):
            raise ValueError(f"invalid groups in {f} (expected mapping)")

        for group_name, group_def in groups.items():
            if group_name not in selected:
                continue
            if not isinstance(group_def, dict):
                raise ValueError(f"invalid group {group_name!r} in {f} (expected mapping)")

            loaded_groups.append(group_name)

            base_gem5 = str(group_def.get("base_gem5", "") or "")
            base_gem5 = _format_macros(base_gem5, macros)

            xs_fmt = group_def.get("xs_fmt")
            if xs_fmt is not None:
                xs_fmt = _format_macros(str(xs_fmt), macros)

            gem5_map = group_def.get("gem5", {}) or {}
            if not isinstance(gem5_map, dict):
                raise ValueError(f"invalid gem5 map for {group_name!r} in {f}")

            xs_map = group_def.get("xs", {}) or {}
            if not isinstance(xs_map, dict):
                raise ValueError(f"invalid xs map for {group_name!r} in {f}")

            derived_map = group_def.get("derived", {}) or {}
            if not isinstance(derived_map, dict):
                raise ValueError(f"invalid derived map for {group_name!r} in {f}")

            for col, suffix in gem5_map.items():
                col = str(col).strip()
                if not col:
                    continue
                if col in gem5_targets and gem5_targets[col] != str(suffix):
                    raise ValueError(f"duplicate gem5 column {col!r} across yaml files/groups")
                full = _join_stat(base_gem5, str(suffix))
                full = _format_macros(full, macros)
                gem5_targets[col] = gem5_glob_to_stat_regex(full)

            for col, xs_val in xs_map.items():
                col = str(col).strip()
                if not col:
                    continue
                if col in xs_targets and xs_targets[col] != str(xs_val):
                    raise ValueError(f"duplicate xs column {col!r} across yaml files/groups")
                xs_val_s = _format_macros(str(xs_val), macros)
                if xs_fmt is not None:
                    xs_targets[col] = xs_fmt.replace("{stat}", xs_val_s)
                else:
                    xs_targets[col] = xs_val_s

            for col, expr in derived_map.items():
                col = str(col).strip()
                if not col:
                    continue
                expr = _format_macros(str(expr), macros)
                if col in derived and derived[col] != expr:
                    raise ValueError(f"duplicate derived column {col!r} across yaml files/groups")
                derived[col] = expr

    missing_groups = sorted(set(selected) - set(loaded_groups))
    if missing_groups:
        raise ValueError(f"unknown groups: {', '.join(missing_groups)}")

    # internal: allow a convenient "domain" prefix if caller wants it later
    _ = domain
    _ = _snake_case
    return LoadedYamlTargets(
        groups=sorted(set(loaded_groups)),
        gem5_targets=gem5_targets,
        xs_targets=xs_targets,
        derived=derived,
    )
