---
name: ghost-rubric
description: Rules for flagging job-description quality issues that feed the ghost-risk score. Use when scoring jobs before save_job_scores.
---
You only judge the job description's quality. The server handles the ATS check, reposts, age, salary, and company health.
Flag, when clearly true:
- no_responsibilities: no concrete duties listed.
- no_team: no team, product, or manager mentioned.
- talent_pool_wording: "future opportunities", "talent pool", "always hiring", "pipeline".
- generic_template: the JD could fit any company; no product or stack details.
- named_hiring_contact: a named recruiter or hiring manager is given (this lowers risk).
Never flag on tone or writing quality alone.
