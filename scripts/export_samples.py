"""Export the eval resumes and job postings for the web demo's "use sample data" option.

The demo uses exactly the data the evals measure. All people are fictional. Usage, from
the project root (re-run whenever evals/recruiting/resumes or jobs change):
    python -m scripts.export_samples
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals" / "recruiting"
OUT = ROOT / "web" / "src" / "lib" / "samples.json"

JOB_LABELS = {
    "senior-fullstack-ph": "Senior Full-Stack Developer (PH ad with biased requirements)",
    "senior-backend-go": "Senior Backend Engineer, Go (Remote APAC)",
    "ml-engineer": "Machine Learning Engineer, Computer Vision",
    "talent-acquisition": "Talent Acquisition Specialist (PH ad with biased requirements)",
    "hr-tech-fullstack": "Full-Stack Engineer, HR Tech",
}


def main() -> None:
    jobs = [
        {"id": job_id, "label": label,
         "text": (EVALS / "jobs" / f"{job_id}.txt").read_text(encoding="utf-8").strip()}
        for job_id, label in JOB_LABELS.items()
    ]
    resumes = [
        {"id": p.stem, "text": p.read_text(encoding="utf-8").strip()}
        for p in sorted((EVALS / "resumes").glob("*.txt"))
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"jobs": jobs, "resumes": resumes}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(jobs)} jobs and {len(resumes)} resumes to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
