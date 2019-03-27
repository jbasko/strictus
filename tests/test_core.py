import abc
from typing import Any, ClassVar, Dict, List

import pytest

from strictus.core import get_schema, is_strictus, strictus, strictus_field


class ExampleEvent(strictus):
    id: str = None
    type: str = None
    time: str = None

    @property
    def path(self):
        return f"/events/{self.type}/{self.id}"


class CustomExampleEvent(ExampleEvent):
    PREFIX: ClassVar[str] = "CUSTOM"

    type: str = "custom"
    comment: str


class ExampleEvents(strictus):
    started: CustomExampleEvent = None
    failed: CustomExampleEvent = None
    completed: CustomExampleEvent = None


class ExampleProcess(strictus):
    id: str = None
    status: str = None
    events: ExampleEvents = strictus_field(default_factory=ExampleEvents)


def test_schema_stored_as_strictus_schema_attribute():
    assert ExampleEvent._strictus_schema


def test_simple_schema():
    ee_schema = get_schema(ExampleEvent)

    assert ee_schema["id"].name == "id"

    assert ee_schema["type"].default is None
    assert ee_schema["type"].has_default

    assert ee_schema["time"].type is str

    assert "path" not in ee_schema


def test_inherited_schema():
    cee = get_schema(CustomExampleEvent)

    assert cee["id"]

    assert cee["type"]
    assert cee["type"].has_default
    assert cee["type"].default == "custom"

    assert cee["time"]

    assert not cee["comment"].has_default


def test_type_hints_from_base_class_act_as_field_definitions():
    class Base(abc.ABC):
        x: int
        y: int = 5

    class A(Base, strictus):
        pass

    assert "x" in get_schema(A)
    assert "y" in get_schema(A)

    assert get_schema(A)["y"].default == 5


def test_nested_schema():
    ep_schema = get_schema(ExampleProcess)
    assert ep_schema["events"].type is ExampleEvents
    assert ep_schema["events"].default_factory is ExampleEvents


def test_strictus_field_is_a_descriptor():

    class A(strictus):
        x: int = 55

    assert isinstance(A.x, strictus_field)
    assert hasattr(A.x, "__get__")
    assert hasattr(A.x, "__set__")

    a = A()
    assert a.x == 55

    a.x = 44
    assert a.x == 44


def test_explicit_strictus_field_in_schema():
    class A(strictus):
        x: int = strictus_field(default=55)

    x_schema = get_schema(A)["x"]
    assert x_schema.type is int
    assert x_schema.default == 55

    assert A().x == 55
    assert A(x=44).x == 44


def test_underscore_prefixed_type_hints_are_ignored():
    class A(strictus):
        _x: int = 0
        _y: str
        z: bool = None

    schema = get_schema(A)
    assert "_x" not in schema
    assert "_y" not in schema
    assert schema["z"].type is bool


def test_field_is_strictus():
    assert not get_schema(ExampleEvent)["id"].is_strictus
    assert get_schema(ExampleProcess)["events"].is_strictus
    assert get_schema(ExampleEvents)["started"].is_strictus


def test_field_is_strictus_container():
    assert not get_schema(ExampleEvent)["id"].is_strictus_container
    assert not get_schema(ExampleProcess)["events"].is_strictus_container
    assert not get_schema(ExampleEvents)["started"].is_strictus_container

    class Item(strictus):
        pass

    class Component(strictus):
        items: List[Item]
        items_by_name: Dict[str, Item]

    assert not Component.items.is_strictus
    assert Component.items.is_strictus_container

    assert not Component.items_by_name.is_strictus
    assert Component.items_by_name.is_strictus_container


def test_init_with_defaults():
    ee = ExampleEvent()
    assert ee.id is None
    assert ee.time is None
    assert ee.type is None
    assert ee.path == "/events/None/None"


def test_init_with_default_factory():
    ep = ExampleProcess()
    assert ep.id is None
    assert ep.status is None
    assert isinstance(ep.events, ExampleEvents)


def test_init_accepts_single_positional_argument_a_dict():
    ee = ExampleEvent({"id": "1", "time": "2", "type": "3"}, type="333")
    assert ee.id == "1"
    assert ee.time == "2"
    assert ee.type == "333"


def test_init_with_custom_values():
    ee = ExampleEvent(id="1", time="2", type="3")
    assert ee.id == "1"
    assert ee.time == "2"
    assert ee.type == "3"


def test_init_parses_nested_stricti():
    ep = ExampleProcess(id="1", events={"started": {"id": "2"}})
    assert ep.id == "1"
    assert ep.events.started.id == "2"


def test_init_parses_nested_strictus_container():
    class Item(strictus):
        id: str = None

    class Collection(strictus):
        items: List[Item]
        by_name: Dict[str, Item]

    collection = Collection({
        "items": [{"id": "1"}, {"id": "2"}],
        "by_name": {
            "first": {"id": "1"},
            "second": {"id": "2"},
        },
    })

    assert len(collection.items) == 2
    assert len(collection.by_name) == 2

    assert collection.items[0].id == "1"
    assert collection.items[1].id == "2"

    assert collection.by_name["first"].id == "1"
    assert collection.by_name["second"].id == "2"


@pytest.mark.parametrize("the_type", [
    bool,
    int,
    float,
    str,
])
def test_init_parses_primitives_and_containers_of_types(the_type):
    class A(strictus):
        x: the_type

        items: List[the_type]
        collection: Dict[str, the_type]

    assert A(x=None).x is None
    assert isinstance(A(x=23).x, the_type)
    assert isinstance(A(x="23").x, the_type)

    assert A(items=[None, None]).items == [None, None]
    assert isinstance(A(items=[23, 24]).items[1], the_type)

    assert A(collection={"y": None}).collection["y"] is None
    assert isinstance(A(collection={"y": 23}).collection["y"], the_type)


def test_init_does_not_touch_untyped_dicts_and_lists():
    class A(strictus):
        payload1: dict
        payload2: Dict
        payload3: Dict[str, Any]
        items1: list
        items2: List
        items3: List[Any]

    a = A()
    assert not hasattr(a, "payload1")
    assert not hasattr(a, "items3")

    a = A(
        payload1={"x": 1, "y": "two"},
        payload2={"x": 1, "y": "two"},
        payload3={"x": 1, "y": "two"},
        items1=[1, "two"],
        items2=[1, "two"],
        items3=[1, "two"],
    )
    assert a.payload1 == {"x": 1, "y": "two"}
    assert a.payload2 == {"x": 1, "y": "two"}
    assert a.payload3 == {"x": 1, "y": "two"}
    assert a.items1 == [1, "two"]
    assert a.items2 == [1, "two"]
    assert a.items3 == [1, "two"]

    assert a.to_dict() == dict(
        payload1={"x": 1, "y": "two"},
        payload2={"x": 1, "y": "two"},
        payload3={"x": 1, "y": "two"},
        items1=[1, "two"],
        items2=[1, "two"],
        items3=[1, "two"],
    )


def test_init_does_not_touch_any_but_does_serialise_stricti():
    class A(strictus):
        anything: Any

    a = A()
    assert not hasattr(a, "anything")

    x1 = ExampleEvent(type="example")
    a = A(anything=x1)
    assert a.anything is x1

    assert a.to_dict() == {
        "anything": {"id": None, "type": "example", "time": None},
    }


def test_init_does_not_accept_unknowns():
    class A(strictus):
        x: int

    with pytest.raises(TypeError):
        A(completely_unknown=1)


def test_field_without_default_is_not_initialised():
    cee = CustomExampleEvent()
    assert not hasattr(cee, "comment")


def test_classvar_not_registered_as_field():
    assert CustomExampleEvent.PREFIX == "CUSTOM"
    assert "PREFIX" not in get_schema(CustomExampleEvent)


def test_fields_by_default_are_included_in_dict_repr():
    f = strictus_field()
    assert f.dict is True

    g = strictus_field(dict=False)
    assert g.dict is False


def test_dict_repr_setting_is_respected():
    class A(strictus):
        x1: int = strictus_field(dict=False)
        x2: int = strictus_field(dict=False, default=22)
        y1: str = strictus_field(dict=True)
        y2: str = strictus_field(dict=True, default="yy")
        z: float

    schema = get_schema(A)
    assert schema["x1"].dict is False
    assert schema["x2"].dict is False
    assert schema["y1"].dict is True
    assert schema["y2"].dict is True
    assert schema["z"].dict is True

    assert A().to_dict() == {"y2": "yy"}
    assert A(x1=1).to_dict() == {"y2": "yy"}
    assert A(x2=222222).to_dict() == {"y2": "yy"}
    assert A(x1=1, x2=222222, y1="y", y2="yyyy", z=3).to_dict() == {
        "y1": "y",
        "y2": "yyyy",
        "z": 3.0,
    }


def test_simple_empty_to_dict():
    ee = ExampleEvent()
    assert ee.to_dict() == {
        "id": None,
        "type": None,
        "time": None,
    }


def test_nested_empty_to_dict():
    ep = ExampleProcess()
    assert isinstance(ep.events, ExampleEvents)
    assert ep.to_dict() == {
        "id": None,
        "status": None,
        "events": {
            "started": None,
            "failed": None,
            "completed": None,
        },
    }


def test_nested_non_empty_to_dict():
    ep = ExampleProcess(
        events={
            "started": {"id": 1, "comment": "started at first"},
            "completed": {"id": 2, "comment": "then completed"},
        })

    assert ep.events.started.id == "1"
    assert ep.events.completed.comment == "then completed"

    assert ep.to_dict() == {
        "id": None,
        "status": None,
        "events": {
            "started": {
                "id": "1",
                "type": "custom",
                "time": None,
                "comment": "started at first",
            },
            "failed": None,
            "completed": {
                "id": "2",
                "type": "custom",
                "time": None,
                "comment": "then completed",
            },
        },
    }


def test_nested_list_of_strictus_to_dict():
    class A(strictus):
        id: int

    class B(strictus):
        items: List[A]

    b = B(items=[{"id": "1"}, {"id": "2"}])
    assert b.items[0].id == 1
    assert b.items[1].id == 2

    assert b.to_dict() == {"items": [{"id": 1}, {"id": 2}]}


def test_nested_dict_of_strictus_to_dict():
    class A(strictus):
        id: int

    class B(strictus):
        collection: Dict[str, A]

    b = B(collection={"first": {"id": "1"}, "second": {"id": "2"}})
    assert b.collection["first"].id == 1
    assert b.collection["second"].id == 2

    assert b.to_dict() == {
        "collection": {
            "first": {"id": 1},
            "second": {"id": 2},
        },
    }


def test_field_with_getter_should_not_allow_setting_value():
    class A(strictus):

        @strictus_field
        def x(self):
            return "xxx"

    a = A()

    assert a.x == "xxx"

    with pytest.raises(AttributeError):
        a.x = "XXX"


def test_read_only_field():
    class A(strictus):
        x: int = strictus_field(read_only=True)

    assert A.x.read_only

    with pytest.raises(AttributeError):
        _ = A().x

    assert A(x=1).x == 1
    assert A(x=1).to_dict() == {"x": 1}

    with pytest.raises(AttributeError):
        A().x = 2


def test_getter_is_not_called_during_initialisation():
    class A(strictus):
        @strictus_field
        def x(self):
            raise RuntimeError()

    class B(strictus):
        a: A = strictus_field(default_factory=A)
        a_list: List[A] = strictus_field(default_factory=list)

    A()
    B()
    B(a=None)
    B(a_list=None)

    assert is_strictus(B().a)

    with pytest.raises(RuntimeError):
        _ = A().x

    with pytest.raises(RuntimeError):
        _ = B().a.x

    with pytest.raises(RuntimeError):
        A().to_dict()


def test_strictus_is_not_copied_implicitly():
    class A(strictus):
        pass

    x = A()
    y = A()

    assert x is not y
    assert A(x) is x
    assert A(y) is y
    assert A(x) is not y


def test_setattr_parses_values():
    class A(strictus):
        w: float
        x: int
        y: str
        z: bool

    class B(strictus):
        key: A
        items: List[A]
        collection: Dict[str, A]

    a = A()

    a.w = None
    assert a.w is None

    a.w = "1.23"
    assert a.w == 1.23

    a.x = None
    assert a.x is None

    a.x = "23"
    assert a.x == 23

    a.y = None
    assert a.y is None

    a.y = 23
    assert a.y == "23"

    a.z = None
    assert a.z is None

    a.z = 1
    assert a.z is True

    b = B()

    b.key = None
    assert b.key is None

    b.key = {}
    assert isinstance(b.key, A)

    b.items = [{"x": "42", "y": 23}]
    assert b.items[0].x == 42
    assert b.items[0].y == "23"

    b.collection = {
        "first": {"x": "42"},
        "second": a,  # Must not be parsed because it is already of the EXACT expected type
    }
    assert b.collection["first"].x == 42
    assert b.collection["second"] is a


def test_equals():
    class Point(strictus):
        x: int = 0
        y: int = 0

    class Line(strictus):
        starts: Point = None
        ends: Point = None

    assert Point() == Point()
    assert Point(x=0, y=0) == Point()
    assert Point(x=1, y=1) == Point(x=1, y=1)
    assert Point(x=1, y=1) != Point()

    assert Line() == Line()
    assert Line(starts={"x": 1, "y": 2}) != Line()
    assert (
        Line(starts=Point(x=1, y=1), ends=Point(x=2, y=2)) ==
        Line(starts=Point(x=1, y=1), ends=Point(x=2, y=2))
    )


def test_cannot_set_arbitrary_attributes_after_initialisation():
    class A(strictus):
        pass

    a = A()
    assert not hasattr(a, "x")

    with pytest.raises(AttributeError):
        a.x = None
    assert not hasattr(a, "x")


def test_can_set_arbitrary_attributes_during_initialisation():
    class A(strictus):
        def _post_init_(self):
            super()._post_init_()
            self.arbitrary_attribute = 123

    assert A().arbitrary_attribute == 123


def test_field_with_any_type_is_not_parsed():
    class A(strictus):
        x: Any

    a = A(x=1)
    assert a.x == 1

    a.x = "1"
    assert a.x == "1"

    obj = object()
    a.x = obj
    assert a.x is obj
