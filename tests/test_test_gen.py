"""Test edge test category selection."""

import pytest
from schemas.problem_spec import Constraints, ConstraintBound
from pipeline.test_gen import select_categories


def test_empty_constraints():
    cats = select_categories(Constraints())
    assert cats == []


def test_int_bound():
    constraints = Constraints(bounds=(
        ConstraintBound(variable="n", min=1, max=100000, kind="int"),
    ))
    cats = select_categories(constraints)
    names = [c["name"] for c in cats]
    assert "n_min" in names
    assert "n_max" in names
    assert "n_large" in names


def test_array_bound():
    constraints = Constraints(bounds=(
        ConstraintBound(variable="a", min=0, max=1000, kind="array"),
    ))
    cats = select_categories(constraints)
    names = [c["name"] for c in cats]
    assert "a_empty" in names
    assert "a_single" in names
    assert "a_all_duplicates" in names


def test_overflow_detection():
    constraints = Constraints(bounds=(
        ConstraintBound(variable="n", min=1, max=3000000000, kind="int"),
    ))
    cats = select_categories(constraints)
    names = [c["name"] for c in cats]
    assert "n_overflow" in names


def test_zero_crossing():
    constraints = Constraints(bounds=(
        ConstraintBound(variable="x", min=-100, max=100, kind="int"),
    ))
    cats = select_categories(constraints)
    names = [c["name"] for c in cats]
    assert "x_zero" in names


def test_no_zero_crossing():
    constraints = Constraints(bounds=(
        ConstraintBound(variable="x", min=1, max=100, kind="int"),
    ))
    cats = select_categories(constraints)
    names = [c["name"] for c in cats]
    assert "x_zero" not in names
