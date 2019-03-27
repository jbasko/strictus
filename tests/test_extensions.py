import abc
from typing import List

import pytest

from strictus.core import get_schema, strictus, strictus_field


def test_update_attributes():
    class A(strictus):
        x: int
        y: int
        label: str = strictus_field(default=None, read_only=True)

    class Collection(strictus):
        points: List[A]

    c = Collection(points=[
        {"x": "1", "y": "11"},
        {"x": "2", "y": "22", "label": "two"},
    ])

    assert c.points[0].label is None
    assert c.points[1].y == 22

    c.points[1].update_attributes(y="33")
    assert c.points[1].y == 33

    c.update_attributes(points=[{"x": "44"}])
    assert c.points[0].x == 44

    with pytest.raises(AttributeError):
        c.points[0].update_attributes(label="should be read-only")


def test_post_init_hook():
    class A(strictus):
        a_post_init_called: bool = False

        def _post_init_(self):
            super()._post_init_()
            self.a_post_init_called = True
            assert self._strictus_initialising is True

    class B(A):
        b_post_init_called: bool = False

        def _post_init_(self):
            super()._post_init_()
            self.b_post_init_called = True
            assert self._strictus_initialising is True

    b = B()
    assert b._strictus_initialising is False
    assert b.a_post_init_called
    assert b.b_post_init_called


def test_incorrect_post_init_implementation_raises_runtime_error():
    class A(strictus):
        def _post_init_(self):
            # Missing super()._post_init_() call
            pass

    with pytest.raises(RuntimeError) as exc_info:
        A()
    assert "forget to call super" in str(exc_info.value)


def test_extract_only_extracts_from_to_dict_output():
    class C(strictus):
        n: int = 0
        o: int = strictus_field(default=1, dict=False)

        @strictus_field(dict=False)
        def p(self):
            return 2

        @strictus_field
        def q(self):
            return 3

    assert C().to_dict() == C()._extract() == {"n": 0, "q": 3}

    assert C()._extract(include=["n"]) == {"n": 0}
    assert C()._extract(exclude=["n"]) == {"q": 3}


def test_create_from():
    class A(strictus):
        x: int
        y: int
        z: int

    class B(strictus):
        w: int
        x: int

    a = A(x=1, y=2, z=3)
    assert B.create_from(a).to_dict() == {"x": 1}

    b = B(w=5, x=6)
    assert A.create_from(b).to_dict() == {"x": 6}

    assert A.create_from(b, y=22, z=33).to_dict() == {"x": 6, "y": 22, "z": 33}

    # override x
    assert A.create_from(b, x=11).to_dict() == {"x": 11}


def test_create_from_extracts_additional_attributes_if_target_allows_additional_attributes():
    class A(strictus):
        x: int
        y: int
        z: int

    class B(strictus):
        class Meta:
            additional_attributes = True

        z: str  # !

    a = A(x=1, y=2, z=3)
    assert B.create_from(a).to_dict() == {"x": 1, "y": 2, "z": "3"}


def test_create_from_does_not_pass_non_init_fields():
    class A(strictus):
        id: str

        @strictus_field
        def path(self):
            return f"/items/{self.id}"

    class B(strictus):
        id: str
        path: str

    b = B(id="123", path="bee-path")
    assert b.path == "bee-path"

    a = A.create_from(b)
    assert a.id == "123"
    assert a.path == "/items/123"


def test_schema_meta():
    class A(strictus):
        pass

    assert get_schema(A).meta == {}
    assert get_schema(A).additional_attributes is False

    class B(strictus):
        class Meta:
            custom_setting = 123
            additional_attributes = True

    assert get_schema(B).meta == {"custom_setting": 123, "additional_attributes": True}
    assert get_schema(B).additional_attributes is True
    assert get_schema(B).custom_setting == 123
    assert not hasattr(B, "Meta")
    assert not hasattr(B(), "Meta")

    class C(B):
        class Meta:
            another_setting = "ccc"

    assert get_schema(C).meta == {"custom_setting": 123, "additional_attributes": True, "another_setting": "ccc"}
    assert not hasattr(C, "Meta")
    assert not hasattr(C(), "Meta")


def test_can_set_additional_attributes_if_allowed_in_meta():
    class A(strictus):
        class Meta:
            additional_attributes = True

    a = A(x=11, y=22)
    assert a.x == 11
    assert a.y == 22
    assert a.to_dict() == {"x": 11, "y": 22}

    assert "x" not in get_schema(A)
    assert "x" not in get_schema(a)

    class B(A):
        pass

    b = B()
    b.x = 11
    assert b.x == 11
    b.y = 22
    assert b.y == 22
    assert b.to_dict() == {"x": 11, "y": 22}

    assert "x" not in get_schema(B)
    assert "x" not in get_schema(b)


def test_forbidden_attributes():
    class A(strictus):
        class Meta:
            additional_attributes = True
            forbidden_attributes = ("y", "z")

    assert A(w=11, x=22).to_dict() == {"w": 11, "x": 22}

    with pytest.raises(TypeError):
        A(w=11, x=22, y=33)

    # create_from should not fail, instead just discard the forbidden ones

    class B(strictus):
        w: int = 11
        x: int = 22
        y: int = 33
        z: int = 44

    a = A.create_from(B())
    assert a.to_dict() == {"w": 11, "x": 22}

    # Derived class should be able to disable additional attributes without having to override
    # forbidden attributes

    class C(A):
        class Meta:
            additional_attributes = False

        w: int
        x: int
        y: int
        z: int

    assert C(w=11, x=22, y=33).to_dict() == {"w": 11, "x": 22, "y": 33}
    assert C.create_from(B()).to_dict() == {"w": 11, "x": 22, "y": 33, "z": 44}


def test_init_all_initialises_attributes_without_default():
    class A(strictus):
        pass

    class B(strictus):
        class Meta:
            init_all = True

        x: int

        @strictus_field
        def y(self):
            return "yyy"

    class CBase(abc.ABC):
        p: int

    class C(CBase, strictus):
        class Meta:
            init_all = True

        q: B
        r: int = 5
        s: List[int] = strictus_field(default_factory=list)

    assert get_schema(A).init_all is False
    assert get_schema(B).init_all is True
    assert get_schema(C).init_all is True

    assert B().x is None
    assert B().y == "yyy"

    assert "p" in get_schema(C)
    assert C().p is None
    assert C().q is None
    assert C().r == 5
    assert C().s == []
