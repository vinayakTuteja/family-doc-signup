# How we decide who hears about an opening first

The rules live in [`app/scoring.py`](../app/scoring.py) and are tested in `tests/test_app.py`.
The privacy notice explains them in plain words. Change all three together.

## Principle

Nobody should be ranked first only for being older, having more diagnoses or visiting doctors
more often. The strongest case for being told first is when a real health need, a lack of
continuity and barriers to care combine to make waiting risky. Everyone also rises the longer
they wait, so no one is left at the bottom.

## Points

| Component | Points | Cap |
| --- | --- | --- |
| Ongoing condition needing regular care | 3 | clinical cap 10 |
| 3+ prescriptions, or medication needing tests or dose changes | 2 | |
| Weakened immune system | 3 | |
| Pregnant or gave birth in the last 12 months | 3 | |
| Mental health condition needing ongoing care | 2 | |
| Hospital stay, surgery or 2+ emergency visits in 12 months | 3 | |
| New diagnosis or test result needing follow-up | 3 | |
| Serious or life-limiting illness | 4 | |
| Each access barrier (newcomer, disability, language, transport, no usable walk-in or virtual care, limited support, financial hardship) | 1 | access cap 4 |
| Unstable housing | 2 | |
| Rural postal code (second character is 0) | 1, automatic | |
| Health need (3+ clinical points) plus at least one barrier | +2 | |
| Age: under 2 / 75+ | 3 | |
| Age: 2 to 17 / 65 to 74 | 1 | |
| Time without a doctor: 6 to 12 months / 1 to 2 years / 2 to 5 years / 5+ years / never in Ontario | 1 / 2 / 3 / 4 / 2 | |
| Every 30 days on our list | 1 | no cap |

Ties go to whoever confirmed their email first.

## Factors considered and left out

| Factor | Why it is not scored |
| --- | --- |
| Family history | Almost everyone could tick it, and it rarely changes the risk of waiting 1 to 3 months |
| Overdue screenings | Nearly everyone without a doctor is overdue, so it does not separate people |
| Major life changes | Covered by the newcomer question and time without a doctor |
| Health system navigation | Self-rated, easy to inflate and stigmatizing to ask |

## Guarding against gaming

- Questions are yes/no categories, never diagnoses.
- Clinical and access points are capped.
- The most objective factors (time without a doctor, waiting time, rural postal code) carry real weight.
- Answers are optional and need separate consent.
