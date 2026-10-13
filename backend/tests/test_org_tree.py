"""
Who sees which part of the organisation tree, and who may change it.
Enforced on the server — these are the rules the tree's buttons mirror.
"""

from __future__ import annotations

import pytest

from app.services import org_tree as T


class U:
    def __init__(self, id, role, tenant_id=1, dept_id=None, name="X"):
        self.id, self.role, self.tenant_id, self.dept_id, self.name = id, role, tenant_id, dept_id, name
        self.email, self.employee_code, self.is_active, self.is_hr = None, None, True, False


SA = U(1, "super_admin", tenant_id=None)
OA = U(2, "tenant_admin", 1)                 # Organisation Admin of TATA
DA = U(3, "org_admin", 1, dept_id=10)        # Department Admin of HR
EMP = U(4, "employee", 1, dept_id=10)
EMP_IT = U(5, "employee", 1, dept_id=11)
DA_IT = U(6, "org_admin", 1, dept_id=11)
OTHER_OA = U(7, "tenant_admin", 2)           # TCS
OTHER_EMP = U(8, "employee", 2, dept_id=20)


def test_scopes():
    assert [T.scope_of(x) for x in (SA, OA, DA, EMP)] == ["platform", "organisation", "department", "self"]
    assert T.scope_of(U(9, "org_admin", 1, dept_id=None)) == "self"     # admin with no department sees only self


@pytest.mark.parametrize("viewer,target,visible", [
    (SA, OTHER_EMP, True), (SA, OA, True),
    (OA, EMP_IT, True), (OA, DA, True), (OA, OTHER_EMP, False), (OA, OTHER_OA, False),
    (DA, EMP, True), (DA, OA, True), (DA, EMP_IT, False), (DA, DA_IT, False), (DA, OTHER_EMP, False),
    (EMP, DA, True), (EMP, OA, True), (EMP, EMP_IT, False), (EMP, DA_IT, False), (EMP, U(9, "employee", 1, 10), False),
    (OA, SA, False),
])
def test_who_sees_whom(viewer, target, visible):
    assert T.in_scope(viewer, target) is visible


def test_who_manages_an_organisation():
    assert T.can_manage_org(SA, 1) and T.can_manage_org(SA, 2)
    assert T.can_manage_org(OA, 1) and not T.can_manage_org(OA, 2)
    assert not T.can_manage_org(DA, 1) and not T.can_manage_org(EMP, 1)
    assert not T.can_manage_org(SA, None)


@pytest.mark.parametrize("viewer,target,can", [
    (SA, OTHER_OA, True), (SA, OTHER_EMP, True), (SA, OA, True),
    (OA, DA, True), (OA, EMP_IT, True), (OA, OTHER_EMP, False), (OA, U(10, "tenant_admin", 1), False),
    (DA, EMP, True), (DA, EMP_IT, False), (DA, DA_IT, False), (DA, OA, False),
    (EMP, EMP_IT, False), (EMP, EMP, False),
])
def test_reset_password_follows_the_hierarchy(viewer, target, can):
    assert T.person(target, viewer)["can_reset"] is can


def test_one_admin_warnings():
    assert T._dept_warnings([]) == ["No Department Admin"]
    assert T._dept_warnings([1]) == []
    assert "2 Department Admins" in T._dept_warnings([1, 2])[0]
    assert T._org_warnings([]) == ["No Organisation Admin"]


def test_initials():
    assert T.initials("Aarti Deshpande") == "AD"
    assert T.initials("Kiran") == "K"
    assert T.initials("  ") == "?"
