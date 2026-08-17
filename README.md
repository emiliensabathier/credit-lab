# credit-lab

Which default score flags first — Altman Z'', Ohlson O, or Merton distance-to-default —
measured against real European credit events, with the false-alarm count and the money
published on the same page.

![ci](https://github.com/emiliensabathier/credit-lab/actions/workflows/ci.yml/badge.svg)

## Results

Thirteen issuers: six that entered a court-supervised restructuring between 2022 and 2024,
seven that did not. A name is flagged when it sits among the three riskiest of the thirteen
and stays there for twenty sessions. Statements are treated as public ninety days after
fiscal year end.

**Lead time before the credit event, in months:**

| | Altman | Ohlson | Merton |
| --- | --- | --- | --- |
| Atos | not in time | not in time | **10.81** |
| Casino Guichard | not in time | not in time | not in time |
| Emeis | not in time | not in time | not in time |
| Samhallsbyggnadsbolaget | **2.14** | not in time | **13.04** |
| Adler Group | not in time | not in time | not in time |
| Intrum | **18.50** | **18.50** | not in time |

**False alarms, in control-name months: 0.00 for all three scores.**

Full report with per-company charts, the event sources and the robustness grid:
[`reports/horserace.html`](reports/horserace.html).

## What this actually shows

Read the two tables together, because separately each one flatters the scores.

No score flags more than two of the five names in the common sub-sample. Three of the six
stressed issuers — Casino, Emeis, Adler — are caught by nothing at all, in time, under any
score. The headline is a row of blanks, and the blanks are the finding.

The zero false-alarm count is real and it is also uninformative here. No control name ever
enters the riskiest three over the window where the cross-section is rankable, under any
score. That reads as clean separation, and it also means the false-alarm counter cannot
discriminate between the three scores on this sample. Both halves of that sentence are true
and the second one is the one usually left out.

## What the lead was worth

A lead time on its own is a number that cannot be wrong. `avoided` is the signed return from
the alarm to the event: negative means the price fell after the alarm, which is what the
warning was worth. `already_suffered` is the fall from the prior twelve-month peak down to
the alarm, which is what the warning had already cost by the time it arrived.

| Ticker | Score | Alarm | Event | avoided | already_suffered | after_target |
| --- | --- | --- | --- | --- | --- | --- |
| SBB-B.ST | Altman | 2024-04-29 | 2024-07-03 | **+0.91** | -0.55 | -0.21 |
| INTRUM.ST | Altman | 2023-05-02 | 2024-11-15 | -0.62 | -0.63 | +0.18 |
| INTRUM.ST | Ohlson | 2023-05-02 | 2024-11-15 | -0.62 | -0.63 | +0.18 |
| ATO.PA | Merton | 2023-05-02 | 2024-03-26 | -0.86 | -0.53 | -0.61 |
| SBB-B.ST | Merton | 2023-06-02 | 2024-07-03 | **+0.40** | -0.70 | -0.21 |

Two of the five alarms were followed by the share price *rising* — 91% and 40%. Those are
not leads, they are warnings that fired at the bottom. Of the three that did precede a fall,
every one arrived after the name had already lost between 53% and 70% from its peak. Intrum's
eighteen-month lead, the longest in the whole study, arrived with the stock already down 63%.

This is the column that turns "which score flags first" into "was any of it worth anything",
and on this sample the answer is: barely, and never early.

## Robustness

Median lead per score, in months, under each convention:

| Variant | Altman | Ohlson | Merton |
| --- | --- | --- | --- |
| headline | 10.32 | 18.50 | 11.93 |
| lag 60 | 11.43 | 19.65 | 13.09 |
| lag 120 | 9.41 | 17.61 | 13.04 |
| persistence 10 | 10.79 | 18.99 | 12.40 |
| persistence 40 | 9.38 | 17.58 | 12.12 |
| tercile | 16.28 | 10.81 | 12.43 |

Publication lag at 60, 90 and 120 days; persistence at 10, 20 and 40 sessions; the riskiest
three against the riskiest four. The last row reverses the ranking: Ohlson leads under every
convention except one, where it comes last. **A ranking that flips between arbitrary
conventions is a null result, and this one reads as a null result.**

## Method

- **Universe frozen before the first run.** `src/clab/universe.py` was committed before any
  score was computed, and no name has been added or removed since. That promise is only worth
  something because of the commit order, which is why it is stated here rather than asserted.
- **Events sourced one by one from primary documents.** No free data source publishes rating
  history. Each date is a court order, a company press release or an agency action, cited in
  `src/clab/events.py`. The rule is uniform: the date the first court-supervised proceeding
  became public; where none exists, the first SD/D rating. SBB is the only name taking the
  fallback.
- **Point-in-time by construction.** An annual report closed on 31 December is not available
  on 31 December. `pointintime.py` expands annual statements onto the daily index starting at
  publication date, ninety days after fiscal year end. The lag is uniform rather than
  per-company: a hand-collected set of real publication dates would be more accurate, but a
  uniform lag applied identically to every name and every year cannot favour one score over
  another, and that property matters more here than accuracy does.
- **The alarm is dated to the twentieth session, not the first.** An observer only knows on
  the twentieth session that the condition held. Dating it to the first would credit the score
  with information that did not exist yet — the same look-ahead the point-in-time layer spends
  its whole existence eliminating. The choice costs all three scores one month, equally.
- **The cross-section must be rankable before anything is flagged.** A date only counts once
  at least twice as many names carry a score as the number being flagged. Below that the rule
  stops selecting and starts describing whoever happens to have data.

## Reproducing the figures

The committed `reports/horserace.html` is rendered from a frozen fixture by
`scripts/build_frozen_report.py`, and a test asserts the committed page and the freshly
rendered one are identical outside the chart images.

Every figure above is pinned, by one of two routes, and the difference is worth stating
rather than blurring:

- the lead times, the false-alarm counts and the common sub-sample are written out as
  literals in `tests/test_regression.py` and compared value by value;
- the impact and robustness tables are pinned by the report-identity test instead. They are
  not restated as literals anywhere, so they are protected only in the sense that changing
  them changes the rendered page, which then stops matching the committed one.

Either way a changed number fails the suite, and either way the cause is one of two
deliberate acts: the model changed, or the fixture was re-captured.

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m clab --refresh      # live pull, writes reports/horserace.local.html
```

A live run never overwrites the committed report. It writes `horserace.local.html`, because
overwriting the committed page would silently break the identity test that makes it
trustworthy.

**The suite takes fifteen to twenty-five minutes.** Four files — `test_pipeline`,
`test_regression`, `test_report`, `test_robustness` — replay the whole frozen pipeline, and
the robustness grid alone runs it six times over. The other sixty-one tests finish in under
six seconds.

## Limitations

Stated because they matter more than the tables.

- **Six events are not a statistic.** Only five carry all three scores. This repository
  measures a handful of histories; it does not test a hypothesis, and no p-value appears
  anywhere in it. Every ranking above should be read as a description of these five names.
- **Casino has no Altman score at all**, because a statement line the formula needs is not
  reported in its filings as loaded. A missing line is not a zero and not a NaN to be filled
  later, so the score refuses; the refusal and its reason are published on the report page
  rather than quietly dropped.
- **Altman here is Z''**, the four-variable variant for non-manufacturers. The original Z is
  deliberately not used: its X4 divides market capitalisation by book liabilities, which
  would make the score move daily and destroy the one comparison the study exists to make —
  annual accounting against daily market data.
- **Emeis has no accounting score in time**, on either measure: its proceeding opened on
  2022-04-20, weeks after FY2021 first became public under the ninety-day lag. A score that
  needs a statement cannot beat an event that arrives before the statement does.
- **The fallen-angel cross-check covers two names.** Only Atos and SBB ever fell below BBB-.
  Casino and Adler were already speculative grade before the window, Emeis has no public S&P
  rating, and Intrum was already below BBB-. Two observations are a cross-check, not a
  statistic, and they are never averaged into the main table.
- **Merton is estimated from equity, not from debt prices.** Distance-to-default here is the
  standard structural inversion of equity value and volatility; it inherits every assumption
  in that, including a single debt point and lognormal asset dynamics.

## Licence

MIT.
