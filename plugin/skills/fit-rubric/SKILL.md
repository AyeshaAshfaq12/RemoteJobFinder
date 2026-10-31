---
name: fit-rubric
description: Rules for scoring how well a job fits the user's Master Profile (match, stretch, reach, skip). Use whenever scoring jobs before save_job_scores.
---
Score fit from the job's real requirements, never from the years number alone.
- List must-haves (explicitly required) and nice-to-haves from the JD.
- For each must-have, cite the profile bullet id that proves it, or record it as a gap.
- A gap is 'low' severity if a profile bullet shows a transferable skill (same category:
  e.g. Rails→Django backend, Redshift→Snowflake); otherwise 'high'.
- match: no high gaps, and years asked ≤ user's years + 1.
- stretch: at most 2 low gaps or 1 high gap, or years asked ≤ user's years + 3.
- reach: anything harder that still shares the core domain.
- skip: different field, or below the user's seniority_floor.
- fit_summary: one sentence, specific, e.g. "Strong FastAPI + Postgres match; no Kubernetes."
