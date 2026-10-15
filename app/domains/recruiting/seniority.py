"""Deterministic seniority. The LLM reports facts (SenioritySignals); code applies the rubric.

Why: in evals, every model judged seniority mostly by job title and rated experienced
candidates without "Senior" in their title as "mid". Rules in code are consistent
across models and easy to audit.

Rubric (first match wins; one rubric for every role type):
    principal  sets direction across an organization
    lead       formally leads or manages a team
    intern     currently a student / only seeking an internship
    junior     under 2 years of professional experience
    senior     5+ years with end-to-end ownership, or a senior title with 3+ years
    mid        everyone else
"""

from app.domains.recruiting.schemas import Seniority, SenioritySignals

JUNIOR_MAX_YEARS = 2
SENIOR_MIN_YEARS = 5
SENIOR_TITLE_MIN_YEARS = 3


def infer_seniority(signals: SenioritySignals, years: float) -> Seniority:
    if signals.org_level_scope:
        return "principal"
    if signals.leads_team:
        return "lead"
    if signals.is_student:
        return "intern"
    if years < JUNIOR_MAX_YEARS:
        return "junior"
    if years >= SENIOR_MIN_YEARS and signals.owns_outcomes:
        return "senior"
    if years >= SENIOR_TITLE_MIN_YEARS and signals.has_senior_title:
        return "senior"
    return "mid"
