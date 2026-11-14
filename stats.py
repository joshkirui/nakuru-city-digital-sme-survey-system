"""Small statistics helpers used by the dashboard (no third-party dependencies)."""

import math


def mean(values):
    return sum(values) / len(values) if values else 0.0


def variance(values, sample=True):
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    ss = sum((v - m) ** 2 for v in values)
    return ss / (n - 1 if sample else n)


def sd(values):
    return math.sqrt(variance(values))


def cronbach_alpha(rows):
    """rows: list of response vectors, one value per item. Requires complete rows."""
    if len(rows) < 2:
        return None
    k = len(rows[0])
    if k < 2:
        return None
    item_vars = [variance([r[j] for r in rows]) for j in range(k)]
    totals = [sum(r) for r in rows]
    total_var = variance(totals)
    if total_var == 0:
        return None
    return (k / (k - 1)) * (1 - sum(item_vars) / total_var)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ---------------------------------------------------------------- distributions


def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    max_iter, eps, fpmin = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_pvalue(t, df):
    if df <= 0:
        return None
    return betai(df / 2.0, 0.5, df / (df + t * t))


def f_pvalue(f, df1, df2):
    if df1 <= 0 or df2 <= 0 or f <= 0:
        return None
    return betai(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


# ---------------------------------------------------------------- regression


def _invert(matrix):
    n = len(matrix)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        aug[col] = [v / pv for v in aug[col]]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor:
                aug[r] = [a - factor * b for a, b in zip(aug[r], aug[col])]
    return [row[n:] for row in aug]


def ols(y, x_rows, labels):
    """Ordinary least squares with an intercept.

    y: response values; x_rows: list of predictor vectors (without intercept);
    labels: names for the predictors.
    """
    n = len(y)
    k = len(labels)
    if n <= k + 1:
        return None
    X = [[1.0] + list(r) for r in x_rows]
    p = k + 1

    xtx = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(p)]
    inv = _invert(xtx)
    if inv is None:
        return None

    coef = [sum(inv[a][b] * xty[b] for b in range(p)) for a in range(p)]
    fitted = [sum(coef[a] * X[i][a] for a in range(p)) for i in range(n)]
    residuals = [y[i] - fitted[i] for i in range(n)]
    ss_res = sum(r * r for r in residuals)
    ybar = mean(y)
    ss_tot = sum((v - ybar) ** 2 for v in y)
    df_res = n - p
    if ss_tot == 0 or df_res <= 0:
        return None
    sigma2 = ss_res / df_res
    se = [math.sqrt(max(sigma2 * inv[a][a], 0.0)) for a in range(p)]
    tvals = [coef[a] / se[a] if se[a] else None for a in range(p)]
    pvals = [t_pvalue(t, df_res) if t is not None else None for t in tvals]
    r2 = 1 - ss_res / ss_tot
    adj_r2 = 1 - (1 - r2) * (n - 1) / df_res if df_res else None
    f_stat = (r2 / k) / ((1 - r2) / df_res) if r2 < 1 else None
    fp = f_pvalue(f_stat, k, df_res) if f_stat else None

    terms = [{
        "label": "Constant",
        "b": coef[0],
        "se": se[0],
        "t": tvals[0],
        "p": pvals[0],
    }]
    for a, name in enumerate(labels, start=1):
        terms.append({
            "label": name,
            "b": coef[a],
            "se": se[a],
            "t": tvals[a],
            "p": pvals[a],
        })
    return {
        "terms": terms,
        "r2": r2,
        "adj_r2": adj_r2,
        "f": f_stat,
        "f_p": fp,
        "n": n,
        "k": k,
    }


def stars(p):
    if p is None:
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""
