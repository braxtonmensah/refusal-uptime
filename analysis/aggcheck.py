"""aggcheck: an aggregate that refuses to be a single number.

Written 2026-10-21 04:42 ET after the same defect hit two lanes in two days, both times with the
preventing rule already in memory and not applied:
  - VCC/Silicyte 10/21: a reachability count tested lowercase 'ok'/'reachable' against values stored
    'REACHABLE', so one lane's checked rows read as zero and a correct credit was nearly withdrawn.
  - 10/19: a PowerShell case-collision ($D vs $d) silently turned an accumulator into a doubler and
    printed a clean 2.000 across a whole sweep.
A rule that lives in memory does not fire. The polling rule in this programme was restated four times in
prose and only stopped when it became a hook that denies the tool call. So this module makes the rule
mechanical: count() returns a Count that carries an independently computed second count and RAISES when
the two disagree, and rate() refuses to return one rate without its partition spread.

Pure stdlib. Import it, or run it for the self-test:  python -I aggcheck.py
"""
from collections import Counter


class AggregateDisagreement(AssertionError):
    """Two independent counts of the same thing disagreed. Do not paper over this: find the bug."""


class EmptyMatchWithCandidates(AssertionError):
    """A predicate matched nothing while plausible values were present.

    ADDED 2026-10-21 04:46 ET by the silicyte lane, with the author's agreement that disagreement
    should raise rather than warn. This closes the one hole this module's own docstring names: two
    independently written predicates CAN share the same misconception. If both ask for lowercase
    'reachable' against data stored as 'REACHABLE', they agree at zero, `count` is satisfied, and
    zero is reported. That is precisely the 04:28 bug, and agreement does not catch it.

    So when a count comes back 0 while the case-folded histogram holds non-null values, that is a
    bug until the caller proves otherwise. Fires only when `field=` was supplied, so it cannot
    surprise a caller that did not opt into the histogram, and it can only fire where the previous
    behaviour was to silently report 0.
    """


def norm(v):
    """Canonical form for a categorical value. Case and surrounding space are never meaningful here."""
    return None if v is None else str(v).strip().lower()


class Count:
    """A count that knows how it was computed twice. Its repr prints both, so a pasted number carries them."""

    def __init__(self, n, n_independent, total, label=""):
        if n != n_independent:
            raise AggregateDisagreement(
                f"{label or 'count'}: primary {n} != independent {n_independent} (of {total}). "
                "Usual causes: case or whitespace in the predicate, a key present but None, "
                "or the two paths disagreeing about what the denominator is."
            )
        self.n, self.total, self.label = n, total, label

    @property
    def rate(self):
        return self.n / self.total if self.total else float("nan")

    def __repr__(self):
        pct = "nan" if self.total == 0 else f"{100 * self.rate:.1f}%"
        return f"{self.label or 'count'} {self.n} of {self.total} = {pct} (two independent counts agree)"


def count(rows, predicate, independent, label="", field=None, expect=None):
    """Count rows two ways and refuse to return one number if they differ.

    predicate   : the reading you mean, e.g. lambda r: norm(r.get('reach')) == 'reachable'
    independent : the SAME question asked differently, ideally not sharing the first one's helpers,
                  e.g. lambda r: 'reach' in r and str(r['reach']).upper().startswith('REACH')
    field       : optional; when given, the value histogram is printed by report() so a silent
                  mismatch (every value 'REACHABLE' while you tested 'ok') is visible, not inferred.
    expect      : optional; the value or values your predicate is meant to match, e.g. 'reachable'
                  or ('reachable', 'ok'). Supplying it makes the empty-match guard PRECISE instead of
                  merely loud, so declare it whenever you pass field=.

    The empty-match guard, and why `expect` matters (VCC lane, 2026-10-21 04:53 ET). Without `expect`
    the guard raises on ANY zero whose field holds other values, which is a false positive on a
    legitimately empty subset: our own register has 43 vcc rows with reach values {None: 32,
    unchecked: 11} and zero reachable, so a CORRECT count raised. The old advice was to drop field=,
    which also throws away the histogram that makes the real bug visible. With `expect` the guard
    fires on the bug's actual signature: the histogram is case-folded, so if your expected value is
    PRESENT in canonical form and you still matched nothing, your predicate is wrong (the 'ok' vs
    'REACHABLE' case); if it is ABSENT, the subset genuinely has none and zero stands.
    """
    rows = list(rows)
    c = Count(sum(1 for r in rows if predicate(r)),
              sum(1 for r in rows if independent(r)), len(rows), label)
    c.hist = dict(Counter(norm(r.get(field)) for r in rows)) if field else None
    if field and c.n == 0 and rows:
        present = sorted(v for v in c.hist if v is not None)
        wanted = [norm(e) for e in ((expect,) if isinstance(expect, str) else (expect or ()))]
        hit = [w for w in wanted if w in present]
        if present and (not wanted or hit):
            why = (f"your expected value(s) {hit} ARE present in canonical form, so the predicate is "
                   f"wrong, not the data" if hit else
                   f"no expect= was declared, so this may be a legitimate empty subset: pass "
                   f"expect=<the value your predicate matches> to make this check precise")
            raise EmptyMatchWithCandidates(
                f"{label or 'count'}: matched 0 of {len(rows)} on field {field!r}, but these "
                f"case-folded values are present: {present[:8]}. {why}. Two independent predicates "
                f"agreeing on zero does not make zero right; they can share one misconception "
                f"(the 2026-10-21 'ok' vs 'REACHABLE' bug)."
            )
    return c


def rate(rows, predicate, independent, partitions, label="", field=None, expect=None):
    """A rate plus its spread across declared partitions. Never return the favourable cut alone.

    partitions: dict name -> filter. DECLARE THESE BEFORE LOOKING AT THE DATA, and include the
    selection-free partition (no outcome conditioning) as the one you quote. Conditioning a rate on the
    outcome enriches for the very defect you are measuring, so such a cut cannot separate mechanism
    from selection and must never be the headline.

    field/expect (silicyte lane, 2026-10-21 04:58 ET): passed through to every per-partition count.
    They were MISSING until now, which was a real hole in the one function built to prevent partition
    errors: `rate` called `count` without `field`, so inside `rate` the histogram was never attached
    and the empty-match guard could never fire. A partition whose predicate is wrong therefore
    reported a silent 0% for that cut, and a wrong 0% in one partition is exactly what widens a spread
    and makes some other cut look like the finding. Declare both whenever the predicate reads a
    categorical field. Defaults are None, so existing callers are unchanged.
    """
    rows = list(rows)
    out = {"ALL (selection-free)": count(rows, predicate, independent, "ALL",
                                         field=field, expect=expect)}
    for name, keep in partitions.items():
        out[name] = count([r for r in rows if keep(r)], predicate, independent, name,
                          field=field, expect=expect)
    vals = [c.rate for c in out.values() if c.total]
    return {
        "headline": out["ALL (selection-free)"],
        "by_partition": out,
        "spread": (min(vals), max(vals)) if vals else None,
        "label": label,
    }


def report(result):
    """Print a rate so that the spread travels with it. A number quoted from here carries its own caveat."""
    h = result["headline"]
    print(f"{result['label'] or 'rate'}: HEADLINE {h!r}")
    if h.hist:
        print(f"  value histogram (case-folded): {h.hist}")
    for name, c in result["by_partition"].items():
        print(f"  {name:<34} {c.n:>4} of {c.total:<4}"
              + ("" if not c.total else f" = {100 * c.rate:.1f}%"))
    lo, hi = result["spread"] or (float("nan"), float("nan"))
    print(f"  SPREAD {100 * lo:.1f}% to {100 * hi:.1f}%"
          f"{'  <- quote the selection-free headline, not the favourable cut' if hi - lo > 0.05 else ''}")


if __name__ == "__main__":
    # Self-test: the two failures this module exists to prevent, plus the case it must not break.
    rows = [{"lane": "arc", "reach": "REACHABLE"}, {"lane": "arc", "reach": "unchecked"},
            {"lane": "vcc"}, {"lane": "vcc", "reach": None}]
    ok = count(rows, lambda r: norm(r.get("reach")) == "reachable",
               lambda r: "reach" in r and str(r["reach"]).upper().startswith("REACH"),
               "reachable", field="reach")
    print(ok)
    assert ok.n == 1
    try:  # the real bug: a lowercase test against uppercase data, caught instead of published
        count(rows, lambda r: r.get("reach") == "reachable",
              lambda r: "reach" in r and str(r["reach"]).upper().startswith("REACH"), "buggy")
    except AggregateDisagreement as e:
        print("CAUGHT, as intended:", str(e).split(".")[0])
    else:
        raise SystemExit("FAILED: the case bug was not caught")
    report(rate(rows, lambda r: norm(r.get("reach")) == "reachable",
                lambda r: "reach" in r and str(r["reach"]).upper().startswith("REACH"),
                {"arc only": lambda r: r["lane"] == "arc", "vcc only": lambda r: r["lane"] == "vcc"},
                "reachability"))
    print("aggcheck self-test OK")
