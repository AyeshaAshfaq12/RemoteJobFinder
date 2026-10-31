---
name: daily-scan
description: Find new remote jobs for the user, score them, and show the shortlist. Use for "find jobs", "daily scan", "anything new?", or when run as a scheduled task.
---
1. Call get_profile. If there is no active profile, ask for the user's CV and stop.
2. Run the crawl_plan queries with web search. Open at most fetch_budget pages in total.
   Prefer pages on ATS domains and company careers pages. Skip pages behind a login.
   For LinkedIn/Indeed results, search for the same title + company on the company's own site instead.
3. From each job page, extract the SubmittedJob fields exactly as written. Never guess a salary or date.
   Skip pages with less than 200 characters of job description.
4. Call submit_jobs in batches of up to 50.
5. For each company in needs_company_check: search news from the last 6 months for layoffs,
   hiring freezes, or funding, then call update_company_health with a source URL.
6. Call search_jobs(only_unscored=true). For each job, apply fit-rubric and the JD flags in ghost-rubric.
   Skip jobs where eligible_for_user is false, unless eligibility is 'unclear' and the JD allows the user's country.
7. Call save_job_scores once with all scores. The shortlist view opens.
8. Reply in at most 3 lines: how many new jobs, how many Match/Stretch, and the single best one with why.
