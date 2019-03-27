from typing import ClassVar

import pytest

from strictus.core import get_schema, strictus, strictus_field


def test_property_is_not_a_field():
    class A(strictus):
        @property
        def x(self) -> str:
            return "xxx"

        y: str

    assert "x" not in get_schema(A)
    assert get_schema(A)["y"]

    assert hasattr(A, "x")
    assert A().x == "xxx"

    assert A().to_dict() == {}
    assert A(y=555).to_dict() == {"y": "555"}

    class B(A):
        pass

    assert "x" not in get_schema(B)
    assert get_schema(B)["y"]
    assert B().to_dict() == {}
    assert B(y=555).to_dict() == {"y": "555"}


def test_strictus_field_without_func_produces_strictus_field_instance():
    f = strictus_field(name="f", type=int)
    assert isinstance(f, strictus_field)
    assert f.name == "f"
    assert f.type is int


def test_calling_strictus_field_with_func_produces_strictus_field_with_getter():
    def x(self, value):
        self._x = value

    f = strictus_field(x)
    assert f.name == "x"
    assert f.getter is x


def test_calling_strictus_field_instance_registers_getter():
    f = strictus_field(name="x")
    assert f.name == "x"

    def x(self) -> str:
        return "normal-x"

    f(x)
    assert f.getter is x
    assert f.type is str

    lambda_getter = lambda self: "lambda-x"
    f(lambda_getter)

    assert f.getter is lambda_getter

    # Getter's name must match the field name
    def bad_getter(self):
        return "bad-x"

    with pytest.raises(ValueError):
        f(bad_getter)


def test_unnamed_field_gets_name_from_getter():
    def zzz(self) -> str:
        return "z-value"

    f1 = strictus_field(zzz)
    assert f1.name == "zzz"
    assert f1.type is str

    f2 = strictus_field()(zzz)
    assert f2.name == "zzz"
    assert f2.type is str


def test_strictus_field_decorated_getters_registered_as_fields():
    class A(strictus):
        @strictus_field
        def x(self) -> str:
            return "xxx"

        @strictus_field(dict=False)
        def y(self) -> int:
            return "yyy"

    x = get_schema(A)["x"]
    assert x.type is str
    assert x.dict is True

    y = get_schema(A)["y"]
    assert y.type is int
    assert y.dict is False

    a = A()
    assert a.x == "xxx"
    assert a.y == "yyy"
    assert a.to_dict() == {
        "x": "xxx",
    }


def test_getter_implies_no_init():
    class A(strictus):

        v: int = strictus_field(init=True)
        w: int

        # a virtual field that is included in the dict output.
        @strictus_field
        def x(self):
            return "xxx"

        # a virtual field that is NOT included in the dict output
        @strictus_field(dict=False)
        def y(self):
            return "yyy"

        z: int = strictus_field(init=False)

    assert A.v.init
    assert A.w.init
    assert not A.x.init
    assert not A.y.init
    assert not A.z.init

    a = A()
    assert a.to_dict() == {"x": "xxx"}

    with pytest.raises(TypeError):
        A(x=1)

    with pytest.raises(TypeError):
        A(y=1)

    with pytest.raises(TypeError):
        A(z=1)

    assert A(v=1, w=1).to_dict() == {"x": "xxx", "v": 1, "w": 1}


def test_properties_not_accepted_as_fields():
    class A(strictus):
        @property
        def x(self):
            return True

    class B(A):
        pass

    with pytest.raises(TypeError):
        A(x=False)

    with pytest.raises(TypeError):
        B(x=False)


def test_default_value_override_in_subclass():
    class A(strictus):
        x: int

    class B(A):
        x: int = 0

    class C(B):
        pass

    class D(C):
        x: int = 5

    class E(D):
        pass

    class F(E):
        pass

    assert A.x.default is strictus.NOT_SET
    assert B.x.default == 0
    assert C.x.default == 0
    assert D.x.default == 5
    assert E.x.default == 5
    assert F.x.default == 5


def test_strictus_field_override():
    class A(strictus):
        x: int = 0

    class B(A):
        x: int = strictus_field(default=55, dict=False, read_only=True, init=False)

    class C(B):
        pass

    assert A.x.default == 0
    assert A.x.dict
    assert A.x.init
    assert not A.x.read_only

    assert B.x.default == 55
    assert B.x.dict is False
    assert B.x.init is False
    assert B.x.read_only

    assert C.x.default == 55
    assert C.x.dict is False
    assert C.x.init is False
    assert C.x.read_only


def test_inherit_getter():
    class A(strictus):
        @strictus_field
        def x(self):
            return f"{self.__class__.__name__}/xxx"

    class B(A):
        pass

    class C(B):
        pass

    assert B().x == "B/xxx"
    assert C().x == "C/xxx"

    with pytest.raises(TypeError):
        B(x=1)

    with pytest.raises(TypeError):
        C(x=1)


def test_override_getter_and_more():
    class A(strictus):
        @strictus_field
        def x(self):
            return "aaa"

    class B(A):
        pass

    class C(B):
        @strictus_field(dict=False)
        def x(self):
            return "ccc"

    class D(C):
        pass

    assert B().x == "aaa"
    assert B.x.dict

    assert C().x == "ccc"
    assert C.x.dict is False

    assert D().x == "ccc"
    assert D.x.dict is False


def test_can_override_field_with_property():
    class A(strictus):
        x: int = 5

    class B(A):
        @property
        def x(self):
            return 55

    assert A().x == 5
    assert isinstance(A.x, strictus_field)

    assert isinstance(B.x, property)
    assert B().x == 55

    with pytest.raises(TypeError):
        B(x=1)

    with pytest.raises(AttributeError):
        B().x = 1


def test_can_override_field_with_annotated_classvar_but_not_with_plain_attribute():
    class A(strictus):
        x: int = 5

    class B(A):
        x: ClassVar[int] = 55

    assert A.x.default == 5

    assert B.x == 55
    assert B().x == 55
    assert "x" not in get_schema(B)

    with pytest.raises(RuntimeError):
        # This is illegal, user probably doing it by mistake.
        # If it's a class var, then should be annotated as such.
        class C(A):
            x = 55

    class D(A):
        x: int = 55

    assert D.x.default == 55
    assert D().x == 55
    assert D(x=1).x == 1

    class E(D):
        # ClassVar argument is not required
        x: ClassVar = 33

    assert E.x == 33
    assert E().x == 33
    assert "x" not in get_schema(E)


def test_field_with_getter_included_in_derived_class_dict():
    class A(strictus):
        id: int = 0

        @strictus_field
        def path(self):
            return f"/items/{self.id}"

    class B(A):
        pass

    assert get_schema(A)["path"].dict
    assert A().to_dict() == {"id": 0, "path": "/items/0"}

    assert get_schema(B)["path"].dict
    assert B().to_dict() == {"id": 0, "path": "/items/0"}


def test_strictus_field_required_option():
    f1 = strictus_field()
    assert not f1.required
    assert not f1.clone().required

    f2 = strictus_field(required=True)
    assert f2.required
    assert f2.clone().required


def test_strictus_field_required_option_enforced():
    class A(strictus):
        x: int = strictus_field(required=True)
        y: int

    class B(A):
        y: int = strictus_field(required=True)
        z: int

    assert A(x=0).x == 0
    assert A(x=0, y=1).to_dict() == {"x": 0, "y": 1}
    with pytest.raises(ValueError):
        A(y=1)

    assert B(x=0, y=1).to_dict() == {"x": 0, "y": 1}
    assert B(x=0, y=1, z=2).to_dict() == {"x": 0, "y": 1, "z": 2}
    with pytest.raises(ValueError):
        B(x=0)
    with pytest.raises(ValueError):
        B(x=0, z=1)


def test_parent_class_property_with_type_hint_higher_up_remains_property():
    class Base:
        x: int

    class A(Base, strictus):
        @property
        def x(self):
            return 55

    class B(A):
        pass

    class C(B):
        pass

    assert "x" not in get_schema(A)
    assert "x" not in get_schema(B)
    assert "x" not in get_schema(C)

    assert A().x == 55
    assert B().x == 55
    assert C().x == 55
