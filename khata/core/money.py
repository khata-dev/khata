"""Money helpers. Internally we work in paise (integer). Floats are only at I/O edges."""

from __future__ import annotations


def rupees_to_paise(rupees: float | int | str | None) -> int:
    if rupees is None or rupees == "":
        return 0
    return round(float(rupees) * 100)


def paise_to_rupees(paise: int | None) -> float:
    if paise is None:
        return 0.0
    return paise / 100.0


def fmt_rupees(paise: int | None) -> str:
    if paise is None:
        return "—"
    r = paise / 100.0
    sign = "-" if r < 0 else ""
    r = abs(r)
    # Indian number formatting: 1,23,456.78
    i, dec = f"{r:.2f}".split(".")
    if len(i) <= 3:
        grouped = i
    else:
        head, tail = i[:-3], i[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        grouped = f"{head},{tail}"
    return f"{sign}₹{grouped}.{dec}"
