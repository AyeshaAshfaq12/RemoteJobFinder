---
name: cv-writer
description: Build a truthful tailored CV (CvContent) and application kit for one job, then call generate_cv. Use for "apply to this", "build my CV for this job", or /apply.
---
Build CvContent for generate_cv.
- Choose 3–6 bullets per recent role that best match the JD's must-haves; drop the rest.
- Rewrite bullets in the JD's vocabulary. Keep every number exactly. Never add a number, tool,
  employer, title, or date that is not in the source bullet. If the JD wants something the profile lacks,
  put it in gap_report with an honest framing; never in the CV.
- Start bullets with a strong verb; one line each where possible; results before tasks.
- Skills: only from profile.skills, JD-relevant ones first, max 24.
- If generate_cv returns validation_failed, fix exactly the listed problems and retry once.
- If it returns too_long, drop the weakest bullets first.
- Kit: cover note ≤180 words, specific to the company; screening answers from profile facts only;
  recruiter DM ≤300 characters.
