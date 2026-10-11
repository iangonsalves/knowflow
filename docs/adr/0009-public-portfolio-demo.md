# ADR 0009 Public portfolio demo

**Status:** Accepted for M8 planning

## Context

KnowFlow is a personal portfolio project. Employers and reviewers need to try the finished product from links on the portfolio website, GitHub and CV. Recurring cloud costs should remain low.

## Decision

M8 must deliver a publicly accessible live demo. At M8, prefer suitable free-tier hosting and services where practical and avoid unnecessary recurring charges. Do not reshape or weaken the approved V1 architecture around a specific hosting provider before deployment evaluation.

## Alternatives

- Local-only demo.
- Select a cloud provider now and tailor the architecture to its free tier.
- Use paid services without evaluating low-cost options.

## Consequences

Choose deployment services at M8 after checking current application needs and free tiers. Public access requires deployment security, quotas/rate limits, secrets, data reset/retention and demo availability decisions at that milestone. No hosting commitment is made now.
