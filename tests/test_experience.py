from datetime import date

import pytest

from app.domains.recruiting.experience import parse_month, total_years_experience
from app.domains.recruiting.schemas import WorkExperience

AS_OF = date(2026, 10, 1)


def role(start, end=None, current=False) -> WorkExperience:
    return WorkExperience(
        company="Co", title="Dev", start_date=start, end_date=end, is_current=current, highlights=[]
    )


MAR_2021 = 2021 * 12 + 2


@pytest.mark.parametrize(
    "value,expected",
    [("2021-03", MAR_2021), ("2021-03-01", MAR_2021), ("2021-03-31", MAR_2021), ("2021", 2021 * 12), (" 2021-3 ", MAR_2021), ("2021/03", MAR_2021),
     ("03/2021", MAR_2021), ("Mar 2021", MAR_2021), ("March 2021", MAR_2021),
     ("mar. 2021", MAR_2021), ("Sept 2021", 2021 * 12 + 8), ("March, 2021", MAR_2021),
     ("2021-13", None), ("Summer 2021", None), ("Present", None), ("", None), (None, None)],
)
def test_parse_month(value, expected):
    assert parse_month(value) == expected


def test_single_closed_role_counts_months_inclusive():
    assert total_years_experience([role("2020-01", "2020-12")], AS_OF) == 1.0


def test_current_role_runs_to_as_of_month():
    assert total_years_experience([role("2025-11", current=True)], AS_OF) == 1.0


def test_overlapping_roles_count_once():
    roles = [role("2020-01", "2021-12"), role("2021-01", "2022-12")]  # 2020..2022
    assert total_years_experience(roles, AS_OF) == 3.0


def test_gaps_are_not_counted():
    roles = [role("2015-01", "2015-12"), role("2020-01", "2020-12")]
    assert total_years_experience(roles, AS_OF) == 2.0


def test_unplaceable_roles_are_skipped():
    roles = [role(None, "2020-12"), role("2019-01", None), role("2020-01", "2020-06")]
    assert total_years_experience(roles, AS_OF) == 0.5


def test_present_text_counts_as_current_even_without_flag():
    assert total_years_experience([role("Nov 2025", "Present")], AS_OF) == 1.0


def test_real_end_date_beats_wrong_current_flag():
    # Seen in eval: model marked an ended job as current.
    assert total_years_experience([role("Jan 2020", "Dec 2020", current=True)], AS_OF) == 1.0


def test_future_end_dates_are_capped():
    assert total_years_experience([role("2026-01", "2030-12")], AS_OF) == 0.83
