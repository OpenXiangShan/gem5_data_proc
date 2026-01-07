import json
import os.path as osp
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Optional, Tuple


_GEM5_MACROS: Dict[str, str] = {
    # matches e.g. "cpu", "cpus", "switch_cpus_1"
    "cpu": r"(?:cpus?|switch_cpus_1)",
    # matches with optional leading "system."
    "syscpu": r"(?:(?:system)\.)?(?:cpus?|switch_cpus_1)",
}


def _glob_to_regex(glob: str, *, macros: Optional[Dict[str, str]] = None) -> str:
    if macros is None:
        macros = {}

    placeholders: Dict[str, str] = {}
    expanded = glob
    for name, rx in macros.items():
        token = f"__MACRO_{name.upper()}__"
        expanded = expanded.replace("{" + name + "}", token)
        placeholders[token] = rx

    rx = re.escape(expanded)
    rx = rx.replace(r"\*", ".*").replace(r"\?", ".")
    for token, token_rx in placeholders.items():
        rx = rx.replace(re.escape(token), token_rx)
    return rx


def gem5_glob_to_stat_regex(glob: str) -> str:
    """
    Convert a "stat-name glob" into a regex fragment that matches the stat name
    in gem5 stats lines (numeric part is appended by gem5_get_stats).
    """
    return _glob_to_regex(glob, macros=_GEM5_MACROS)


@dataclass(frozen=True)
class ExtraTargets:
    gem5: Dict[str, str]
    xs: Dict[str, str]


def parse_extra_target_specs(specs: Iterable[str]) -> ExtraTargets:
    """
    Parse CLI specs like:
      - "foo=cpus.ipc" (gem5 glob by default)
      - "gem5:foo=cpus.ipc"
      - "gem5-re:foo=(?:cpus?|switch_cpus_1)\\.ipc"
      - "xs:foo=\\[PERF \\].*: (\\d+)"
    """
    gem5: Dict[str, str] = {}
    xs: Dict[str, str] = {}

    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"invalid --extra-target: {spec!r} (expected name=pattern)")

        head, pattern = spec.split("=", 1)
        scope = "gem5"
        name = head
        if ":" in head:
            scope, name = head.split(":", 1)

        scope = scope.strip()
        name = name.strip()
        pattern = pattern.strip()
        if not name or not pattern:
            raise ValueError(f"invalid --extra-target: {spec!r} (empty name/pattern)")

        if scope in ("gem5", "g"):
            gem5[name] = gem5_glob_to_stat_regex(pattern)
        elif scope in ("gem5-re", "g-re", "gem5_regex"):
            gem5[name] = pattern
        elif scope in ("xs", "x"):
            xs[name] = pattern
        else:
            raise ValueError(
                f"invalid --extra-target scope {scope!r} in {spec!r}; "
                "use gem5:, gem5-re:, or xs:"
            )

    return ExtraTargets(gem5=gem5, xs=xs)


def load_extra_targets_file(path: str) -> ExtraTargets:
    """
    Load extra targets from a JSON file.

    Supported formats:
      1) {"gem5_glob": {"k":"pat"}, "gem5_regex": {...}, "xs_regex": {...}}
      2) {"gem5": {"k":"pat"}, "xs": {"k":"regex"}}  # gem5 treated as glob
      3) [{"name":"k","gem5":"pat","xs":"regex","gem5_type":"glob|regex"}]
    """
    with open(path, "r") as f:
        data = json.load(f)

    gem5: Dict[str, str] = {}
    xs: Dict[str, str] = {}

    def add_gem5_glob(d: Dict[str, str]) -> None:
        for k, v in d.items():
            gem5[str(k)] = gem5_glob_to_stat_regex(str(v))

    def add_gem5_regex(d: Dict[str, str]) -> None:
        for k, v in d.items():
            gem5[str(k)] = str(v)

    def add_xs_regex(d: Dict[str, str]) -> None:
        for k, v in d.items():
            xs[str(k)] = str(v)

    if isinstance(data, dict):
        if "gem5_glob" in data or "gem5_regex" in data or "xs_regex" in data:
            add_gem5_glob(data.get("gem5_glob", {}))
            add_gem5_regex(data.get("gem5_regex", {}))
            add_xs_regex(data.get("xs_regex", {}))
        else:
            add_gem5_glob(data.get("gem5", {}))
            add_xs_regex(data.get("xs", {}))
    elif isinstance(data, list):
        for row in data:
            if not isinstance(row, dict) or "name" not in row:
                raise ValueError("invalid extra-targets list entry (expected object with 'name')")
            name = str(row["name"])
            gem5_pat = row.get("gem5")
            xs_pat = row.get("xs")
            gem5_type = str(row.get("gem5_type", "glob"))
            if gem5_pat is not None:
                if gem5_type == "glob":
                    gem5[name] = gem5_glob_to_stat_regex(str(gem5_pat))
                elif gem5_type == "regex":
                    gem5[name] = str(gem5_pat)
                else:
                    raise ValueError(f"invalid gem5_type {gem5_type!r} for {name!r}")
            if xs_pat is not None:
                xs[name] = str(xs_pat)
    else:
        raise ValueError("invalid extra-targets JSON (expected object or list)")

    return ExtraTargets(gem5=gem5, xs=xs)


def merge_extra_targets(
    targets: Dict[str, str],
    *,
    xs_stat_fmt: bool,
    extra: ExtraTargets,
) -> Dict[str, str]:
    if xs_stat_fmt:
        return {**extra.xs, **targets}
    return {**extra.gem5, **targets}


def filter_keys_by_globs(keys: Iterable[str], globs: List[str]) -> List[str]:
    if not globs:
        return list(keys)
    patterns = [re.compile("^" + _glob_to_regex(g) + "$") for g in globs]
    kept: List[str] = []
    for k in keys:
        if any(p.search(k) for p in patterns):
            kept.append(k)
    return kept

