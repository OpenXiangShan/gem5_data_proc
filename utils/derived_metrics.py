import ast
from typing import Dict, Union

import numpy as np
import pandas as pd


class UnsafeExpressionError(ValueError):
    pass


_Number = Union[int, float, np.number]
_Value = Union[pd.Series, _Number]


def _ensure_series(v: _Value, index: pd.Index) -> pd.Series:
    if isinstance(v, pd.Series):
        return v
    return pd.Series([float(v)] * len(index), index=index)


def _eval_ast(node: ast.AST, df: pd.DataFrame) -> _Value:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, df)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f"unsupported constant: {node.value!r}")

    # Python <3.8 compatibility (still safe to keep)
    if isinstance(node, ast.Num):  # pragma: no cover
        return node.n

    if isinstance(node, ast.Name):
        name = node.id
        if name not in df.columns:
            raise KeyError(name)
        return df[name]

    if isinstance(node, ast.UnaryOp):
        v = _eval_ast(node.operand, df)
        if isinstance(node.op, ast.UAdd):
            return v
        if isinstance(node.op, ast.USub):
            return -v
        raise UnsafeExpressionError(f"unsupported unary op: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, df)
        right = _eval_ast(node.right, df)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        raise UnsafeExpressionError(f"unsupported binary op: {type(op).__name__}")

    # Disallow everything else: calls, attributes, subscripts, etc.
    raise UnsafeExpressionError(f"unsupported expression node: {type(node).__name__}")


def eval_derived_expr(expr: str, df: pd.DataFrame) -> pd.Series:
    tree = ast.parse(expr, mode="eval")
    v = _eval_ast(tree, df)
    out = _ensure_series(v, df.index)
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def apply_derived_metrics(df: pd.DataFrame, derived: Dict[str, str]) -> pd.DataFrame:
    """
    Apply derived metrics defined as simple arithmetic expressions over existing columns.

    - Missing input columns -> output column is NaN
    - Division-by-zero -> inf -> converted to NaN
    """
    if not derived:
        return df

    for col, expr in derived.items():
        try:
            df[col] = eval_derived_expr(expr, df)
        except KeyError:
            df[col] = np.nan
        except (SyntaxError, UnsafeExpressionError, TypeError, ValueError):
            df[col] = np.nan
    return df

