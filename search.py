import os
import threading
import unicodedata

import pandas as pd

CSV_PATH = os.path.join(os.path.dirname(__file__), "stock.csv")


def _normalize(text: str) -> str:
    """Minúsculas + quita acentos (é→e, ú→u, etc.)."""
    return unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode("ascii")


_df: pd.DataFrame = pd.DataFrame()
_norm_combined: pd.Series = pd.Series(dtype=str)
_reload_lock = threading.Lock()


def _load() -> pd.DataFrame:
    raw = pd.read_csv(
        CSV_PATH,
        sep=";",
        encoding="utf-8-sig",
        skiprows=[0, 1, 2, 3, 4],
        header=0,
        dtype=str,
        skip_blank_lines=True,
    )
    raw = raw.iloc[:, :2]
    raw.columns = ["codigo", "descripcion"]
    df = raw.copy()
    df["codigo"]      = df["codigo"].fillna("").str.strip()
    df["descripcion"] = df["descripcion"].fillna("").str.strip()
    df = df[
        (df["codigo"] != "")
        & (df["codigo"] != "Código")
        & (~df["codigo"].str.startswith(" "))
        & (~df["descripcion"].str.contains("Sub Total", na=False))
        & (df["codigo"].str.len() <= 30)
    ]
    return df.reset_index(drop=True)


def reload_stock() -> None:
    """Atomic reload: builds new df + index, then swaps in one step under lock."""
    global _df, _norm_combined
    new_df = _load()
    new_norm = (new_df["codigo"] + " " + new_df["descripcion"]).apply(_normalize)
    with _reload_lock:
        _df = new_df
        _norm_combined = new_norm


reload_stock()


_STOPWORDS = {
    "que", "cual", "cuales", "tienen", "tenes", "hay", "tiene",
    "disponibles", "disponible", "disponibilidad", "busco", "busca",
    "buscar", "necesito", "quiero", "quisiera", "para", "con", "sin",
    "por", "del", "los", "las", "una", "uno", "son", "sus", "tipo",
    "algo", "sobre", "mas", "muy", "ser", "nos", "unas", "unos",
}


def _extract_keywords(query: str) -> list[str]:
    tokens = _normalize(query).split()
    keywords = []
    for tok in tokens:
        tok = tok.strip("¿?¡!.,;:\"'()[]{}/*+-")
        if len(tok) >= 3 and tok not in _STOPWORDS:
            keywords.append(tok)
    return keywords


def search_stock(query: str, limit: int = 200, offset: int = 0) -> dict:
    """Busca en codigo y descripcion. Devuelve resultados ranqueados + paginables.

    Returns {'items': [...], 'total': int, 'truncated': bool, 'offset': int}.
    Ranking: substring de la query completa > densidad de keywords.
    """
    with _reload_lock:
        df = _df
        norm = _norm_combined

    empty = {"items": [], "total": 0, "truncated": False, "offset": offset}
    if df.empty or not query.strip():
        return empty

    keywords = _extract_keywords(query)
    if not keywords:
        return empty

    # Mask AND: todos los keywords presentes
    and_mask = pd.Series([True] * len(df), index=df.index)
    for kw in keywords:
        and_mask &= norm.str.contains(kw, regex=False)
    matched_idx = df.index[and_mask]

    # Si AND no da resultados, caer a OR
    if len(matched_idx) == 0:
        or_mask = pd.Series([False] * len(df), index=df.index)
        for kw in keywords:
            or_mask |= norm.str.contains(kw, regex=False)
        matched_idx = df.index[or_mask]

    if len(matched_idx) == 0:
        return empty

    # Ranking: substring full query + densidad de keywords
    sub_norm = norm.loc[matched_idx]
    full_query_norm = _normalize(query.strip())
    scores = pd.Series([0] * len(matched_idx), index=matched_idx, dtype=int)
    # Bonus grande si aparece la query completa como substring
    if len(full_query_norm) >= 3:
        scores += sub_norm.str.contains(full_query_norm, regex=False).astype(int) * 100
    # Densidad de keywords (suma de ocurrencias)
    for kw in keywords:
        scores += sub_norm.str.count(kw)

    # Ordenar por score desc, manteniendo orden original para empates
    sorted_idx = scores.sort_values(ascending=False, kind="stable").index

    total = len(sorted_idx)
    offset = max(0, int(offset))
    page_idx = sorted_idx[offset:offset + limit]
    items = df.loc[page_idx, ["codigo", "descripcion"]].to_dict(orient="records")

    return {
        "items": items,
        "total": total,
        "truncated": offset + len(items) < total,
        "offset": offset,
    }


def catalog_size() -> int:
    return len(_df)
