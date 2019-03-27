from typing import Any, Callable, ClassVar, Dict, List, Optional, Type, Union, get_type_hints

from cached_property import cached_property


class _Empty:
    def __init__(self, name="EMPTY"):
        self._name = name

    def __bool__(self):
        return False

    def __repr__(self):
        return self._name


_NOT_SET = _Empty("NOT_SET")


class StrictusSchema(Dict[str, "strictus_field"]):

    meta: Dict[str, Any]

    def __init__(self, *args, **kwargs):
        self.meta = {}
        super().__init__(*args, **kwargs)

    @property
    def additional_attributes(self) -> bool:
        """
        True if the schema allows setting unknown attributes both during and after strictus initialisation.
        """
        return self.meta.get("additional_attributes", False)

    @cached_property
    def forbidden_attributes(self) -> List[str]:
        """
        This only applies to schemas with additional_attributes set to True.
        List of attribute names that should not be allowed on this object even when
        additional attributes are allowed.
        """
        return self.meta.get("forbidden_attributes", [])

    @property
    def init_all(self) -> bool:
        return self.meta.get("init_all", False)

    def __getattr__(self, name):
        if name in self.meta:
            return self.meta[name]
        raise AttributeError(name)


class strictus:
    """

    Usage:

        class Point(strictus):
            x: int = 0
            y: int = 0

        class Line(strictus):
            start_point: Point = strictus_field(default_factory=Point)
            end_point: Point = strictus_field(default_factory=Point)

    To customise, use _post_init_ hook. Do not implement __init__.

    To allow additional attributes:

        class A(strictus):
            class Meta:
                additional_attributes = True

    If additional attributes are enabled, all additional attributes will be included
    in the dict output.

    """

    NOT_SET = _NOT_SET

    _strictus_schema: ClassVar[StrictusSchema]

    _strictus_additional_attributes: Dict[str, Any]
    _strictus_initialising: bool

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        parent_schema: StrictusSchema = StrictusSchema()
        if hasattr(cls, "_strictus_schema"):
            parent_schema = getattr(cls, "_strictus_schema")

        cls._strictus_schema = StrictusSchema()

        schema = cls._strictus_schema
        schema.meta.update(parent_schema.meta)

        if "Meta" in cls.__dict__ and isinstance(cls.__dict__["Meta"], type):
            for k, v in cls.__dict__["Meta"].__dict__.items():
                if not k.startswith("__"):
                    schema.meta[k] = v
            delattr(cls, "Meta")

        names_seen = set()

        # typing.get_type_hints returns annotations merged over all base classes, but
        # to detect ambiguous overrides of strictus fields we need to know whether the
        # class attribute has an annotation in the class itself.
        own_type_hints = cls.__dict__.get("__annotations__", {})

        for name, type_hint in get_type_hints(cls).items():
            names_seen.add(name)

            if name.startswith("_"):
                continue

            if str(type_hint).startswith("typing.ClassVar"):
                continue

            if name in cls.__dict__:
                if isinstance(cls.__dict__[name], strictus_field):
                    schema[name] = cls.__dict__[name]
                    if schema[name].name:
                        # The name of the attribute in the type hint has to match
                        # the name of the field, if specified.
                        assert schema[name].name == name
                    else:
                        schema[name].name = name

                    if not schema[name].has_type:
                        # type= passed to strictus_field overrides the type hint.
                        schema[name].type = type_hint
                else:
                    if hasattr(cls.__dict__[name], "__get__"):
                        # We have a type hint, yet it's a descriptor.
                        # Descriptors (@property) don't get picked up by get_type_hints
                        # so the type hints must be inherited and the descriptor is
                        # overriding the strictus field.
                        # This means we should not include it in the schema and leave as is.
                        continue

                    class_attr_value = cls.__dict__[name]

                    if name in parent_schema and name not in own_type_hints:
                        raise RuntimeError(
                            f"Ambiguous attribute {name} in class {cls.__name__}. "
                            "If you want it to be a class variable, annotate it with ClassVar: "
                            f"'{name}: ClassVar = {class_attr_value}'. "
                            "Or, if you want to override the strictus field of the parent class, "
                            "you must specify a type hint, for example, "
                            f"'{name}: {parent_schema[name].type.__name__} = {class_attr_value}'"
                        )

                    # Not a property, so it's safe to use its value as the default
                    schema[name] = strictus_field(name=name, type=type_hint, default=class_attr_value)

            elif name in parent_schema:
                # Field is not mentioned in the class definition, type hint was inherited
                schema[name] = parent_schema[name].clone()

            elif name not in own_type_hints:
                # The name has a type hint somewhere higher up in the class hierarchy.

                if hasattr(cls, name):
                    if hasattr(getattr(cls, name), "__get__"):
                        # it's a property somewhere higher up, don't touch it
                        continue
                    else:
                        # It's a new field defined in parent class which is not a strictus class,
                        # and this field has a default value
                        schema[name] = strictus_field(name=name, type=type_hint, default=getattr(cls, name))
                        continue
                else:
                    # It's a new field defined in parent class which is not a strictus class,
                    # and the field does NOT have a default value
                    schema[name] = strictus_field(name=name, type=type_hint)
                    continue

            else:
                # Field is declared in this class, but does not have a default value set
                schema[name] = strictus_field(name=name, type=type_hint)

        # Register in schema the fields created with @strictus_field decorator
        for name, value in cls.__dict__.items():
            if name not in names_seen and isinstance(value, strictus_field):
                names_seen.add(name)
                assert name == value.name
                schema[name] = value

        # Clone into schema any inherited fields that weren't mentioned in this class body.
        for name in parent_schema:
            if name not in names_seen:
                schema[name] = parent_schema[name].clone()

        # Override all attributes matching schema items by name
        for name, value in schema.items():
            setattr(cls, name, value)

    def __new__(cls, dict_or_strictus: Union[Dict, "strictus"] = None, **kwargs):

        if cls is strictus:
            raise RuntimeError(f"Trying to instantiate {cls} which should only be used as a base class")

        # An instance of strictus is considered complex and is not copied implicitly - return itself.
        if is_strictus(dict_or_strictus) and issubclass(type(dict_or_strictus), cls):
            return dict_or_strictus

        if dict_or_strictus is not None and not isinstance(dict_or_strictus, dict):
            raise ValueError(f"Expected a dictionary, got a {type(dict_or_strictus)}")

        schema = get_schema(cls)
        instance = super().__new__(cls)

        values = {}
        if dict_or_strictus:
            values.update(dict_or_strictus)
        values.update(kwargs)

        # Keep track of not processed keys
        keys = set(values.keys())

        # Mark the instance is being initialised which means read-only fields can be set
        instance._strictus_initialising = True

        for field in schema.values():
            if field.name in keys:
                keys.remove(field.name)

            # Ensure required fields are present. None is a valid value.
            if field.required and field.name not in values:
                raise ValueError(f"{cls.__name__} field {field.name!r} is required")

            if field.name in values:
                if not field.init:
                    raise TypeError(f"{instance.__class__.__name__}.{field.name} is a non-init field")
                setattr(instance, field.name, values[field.name])
            elif field.default_factory is not _NOT_SET:
                setattr(instance, field.name, field.default_factory())
            elif field.default is not _NOT_SET:
                setattr(instance, field.name, field.default)
            elif field.init and schema.init_all:
                setattr(instance, field.name, None)

        instance._strictus_additional_attributes = {}

        if keys:
            if schema.additional_attributes:
                for k in keys:
                    if k in schema.forbidden_attributes:
                        raise TypeError(
                            f"{instance.__class__.__name__} forbids additional field {k!r}"
                        )
                    instance._set_additional_attribute(k, values[k])
            else:
                raise TypeError(
                    f"Unexpected keyword arguments supplied to "
                    f"{instance.__class__.__name__}: {keys}"
                )

        # Call the post init hook BEFORE sealing the read-only attributes.
        instance._strictus_base_post_init_reached = False
        instance._post_init_()

        # Make sure the base _post_init_ was reached.
        # If it wasn't, user has failed to call super()._post_init_
        if not instance._strictus_base_post_init_reached:
            raise RuntimeError(f"Did you forget to call super()._post_init_() in {cls}._post_init_?")

        # Seal the read-only attributes
        instance._strictus_initialising = False

        return instance

    def to_dict(self) -> Dict:
        dct = {}
        for field in self._strictus_schema.values():
            if not field.dict:
                continue
            try:
                value = getattr(self, field.name)
            except AttributeError:
                continue
            if value is None:
                dct[field.name] = None
            elif is_strictus(value):
                dct[field.name] = value.to_dict()
            elif field.is_strictus_container:
                if field.is_list:
                    dct_value = []
                    for item in value:
                        if item is None:
                            dct_value.append(item)
                        elif is_strictus(item):
                            dct_value.append(item.to_dict())
                        else:
                            raise TypeError(f"Expected None or strictus, got {type(item)} in {field.name}")
                    dct[field.name] = dct_value
                elif field.is_dict:
                    dct_value = {}
                    for k, v in value.items():
                        if v is None:
                            dct_value[k] = v
                        elif is_strictus(v):
                            dct_value[k] = v.to_dict()
                        else:
                            raise TypeError(f"Expected None or strictus, got {type(v)} in {field.name}")
                    dct[field.name] = dct_value
                else:
                    raise NotImplementedError()
            else:
                dct[field.name] = value
        if self._strictus_schema.additional_attributes:
            dct.update(self._strictus_additional_attributes)
        return dct

    def __eq__(self, other):
        if other is None:
            return False
        if other is self:
            return True
        if self.__class__ != other.__class__:
            return False
        return self.__dict__ == other.__dict__

    def __setattr__(self, name, value):
        can_set_attribute = (
            name.startswith("_strictus") or
            self._strictus_initialising or
            name in self.__dict__ or
            (
                name in self._strictus_schema
                # read_only is checked in strictus_field.__set__
            )
        )
        if can_set_attribute:
            super().__setattr__(name, value)
            return
        elif self._strictus_schema.additional_attributes:
            self._set_additional_attribute(name, value)
            return
        raise AttributeError(name)

    def __getattr__(self, name):
        if self._strictus_schema.additional_attributes:
            if name in self._strictus_additional_attributes:
                return self._strictus_additional_attributes[name]
        raise AttributeError(
            f"{self.__class__.__name__} does not have attribute {name}"
        )

    def _set_additional_attribute(self, name, value):
        self._strictus_additional_attributes[name] = value

    # Extensions

    def update_attributes(self, strictus_attributes: Dict = None, exclude: List[str] = None, **kwargs):
        """
        Update attributes in bulk either from the first positional argument - a dictionary -
        or, from **kwargs.
        Names listed in exclude= will be skipped.
        """
        values = {}
        if strictus_attributes:
            values.update(strictus_attributes)
        values.update(kwargs)

        exclude = exclude or ()

        for k, v in values.items():
            if k not in exclude:
                setattr(self, k, v)

    def _extract(
        self: Union["strictus", Any],
        target: Type["strictus"] = None,
        *,
        exclude: List[str] = None,
        include: List[str] = None,
    ) -> Dict:
        """
        Extract attributes from self which can be either a strictus or any object.
        If self is a strictus then the extraction is via to_dict() method -- the values
        extracted are "serialised".

        The target is a strictus type.
        If the target allows additional attributes, the extract will include attributes
        of the source that don't have a counterpart in the target.

        This method allows creation of a strictus of one type from a strictus of a different
        type using this notation:

            source: XType = XType()
            target: YType = source._extract(YType)

        If self (in the context of this method, so source in the example above) is not
        a strictus, then use the create_from class method:

            target: YType = YType.create_from(source)

        """

        if target is None:
            target = self.__class__

        target_schema = get_schema(target)
        attr_names = set(target_schema)

        # Greedy extraction of additional attributes is supported only if the source is a strictus.
        # is_strictus(self) may look weird, but this method is called as a class method from create_from.
        if target_schema.additional_attributes and is_strictus(self):
            attr_names.update(set(get_schema(self)))

        if exclude:
            assert not include
            include = [k for k in attr_names if k not in exclude]
        elif include:
            include = [k for k in attr_names if k in include]
        else:
            include = attr_names

        if is_strictus(self):
            dct = {k: v for k, v in self.to_dict().items() if k in include}
        else:
            dct = {}
            for k in include:
                if hasattr(self, k):
                    dct[k] = getattr(self, k)

        return dct

    @classmethod
    def create_from(
        cls,
        attributes_source: Any,
        *,
        exclude: List[str] = None,
        include: List[str] = None,
        **extras,
    ):
        """
        This method is really an ANTI-PATTERN. You should be using clear mappings instead.

        Creates a new instance of this strictus type by extracting attributes from the source.
        The source doesn't have to be a strictus.
        Pass attributes_source as a positional argument.

        If the target class allows additional attributes then all attributes will be extracted
        except those marked as forbidden (see StrictusSchema)
        """
        extracted_attributes = cls._extract(
            self=attributes_source,
            target=cls,
            exclude=exclude,
            include=include,
        )

        # Exclude non-init fields
        target_schema = get_schema(cls)
        for f in target_schema.values():
            if not f.init and f.name in extracted_attributes:
                del extracted_attributes[f.name]

        # Exclude forbidden fields but only if additional attributes are permitted
        if target_schema.additional_attributes:
            for k in target_schema.forbidden_attributes or ():
                if k in extracted_attributes:
                    del extracted_attributes[k]

        return cls(
            extracted_attributes,
            **extras,
        )

    def _post_init_(self):
        """
        _post_init_ hook is called on every newly created instance of strictus after all attributes
        have been initialised, but before the read-only attributes are sealed.
        """
        self._strictus_base_post_init_reached = True


class strictus_field:

    def __init__(
        self,
        func: Callable = None,
        *,
        name: str = None,
        type: Type[Any] = _NOT_SET,
        default: Any =_NOT_SET,
        default_factory: Callable =_NOT_SET,
        list_container_cls: Type = list,
        dict_container_cls: Type = dict,
        dict: bool = True,
        init: bool = _NOT_SET,
        read_only: bool = False,
        required: bool = False,
    ):
        self.name = name

        self.default = default
        self.default_factory = default_factory

        # A read-only field can only be set during initialisation
        self.read_only = read_only

        # A required field must be passed on initialisation
        # None is a valid value. All that matters is that it is included in the payload.
        self.required = required

        # type is a property which controls a few attributes, do not modify
        # the other attributes directly, modify just the type
        self._type = None
        self._type_args: List = []
        self._is_strictus_container = None
        self._is_dict = None
        self._is_list = None
        self.type = type

        self.list_container_cls = list_container_cls
        self.dict_container_cls = dict_container_cls

        # Whether the field is included in the to_dict() output
        self.dict = dict

        # Whether the field value can be passed to __init__.
        # Implicitly set to False if a custom getter is registered.
        # Otherwise, set to True if not explicitly set to False.
        self._init = init

        self._getter: Callable = None
        if func is not None:
            if self._init is _NOT_SET:
                self._init = False
            self.getter = func

        if self.getter and self.required:
            raise ValueError(f"Inconsistent field {self.name!r} definition: it is both required and has a getter")

    @property
    def type(self) -> Type:
        return self._type

    @type.setter
    def type(self, value):
        self._type = value
        type_str = str(value)
        self._is_list = type_str.startswith("typing.List")
        self._is_dict = type_str.startswith("typing.Dict")
        self._type_args = []
        if self._type is not None:
            self._type_args = getattr(self._type, "__args__", None) or []
            self._is_strictus_container = (
                (self._is_list and is_strictus(self.item_type)) or
                (self._is_dict and is_strictus(self.item_type))
            )

    @property
    def has_type(self) -> bool:
        return self.type is not _NOT_SET

    @property
    def has_default(self) -> bool:
        return not (self.default is _NOT_SET and self.default_factory is _NOT_SET)

    @property
    def is_strictus(self) -> bool:
        return hasattr(self.type, "_strictus_schema")

    @property
    def is_strictus_container(self) -> bool:
        return self._is_strictus_container

    @property
    def item_type(self) -> Optional[Type]:
        if self.is_list:
            if self._type_args:
                return self._type_args[0]
            return None
        elif self.is_dict:
            if self._type_args:
                return self._type_args[1]
            return None
        else:
            raise ValueError(f"{self.__class__.__name__} is not a container hence does not have item type set")

    @property
    def is_list(self) -> bool:
        return self._is_list

    @property
    def is_dict(self) -> bool:
        return self._is_dict

    def clone(self, name: str = None, type: Type[Any] = None):
        return self.__class__(
            func=self.getter,
            name=name or self.name,
            default=self.default,
            default_factory=self.default_factory,
            read_only=self.read_only,
            required=self.required,
            type=type or self.type,
            list_container_cls=self.list_container_cls,
            dict_container_cls=self.dict_container_cls,
            dict=self.dict,
            init=self.init,
        )

    @property
    def init(self) -> bool:
        """
        Returns True if this field is accepted by __init__.

        This is initialised in one of the following ways:
        - explicitly by passing init= to the strictus_field
        - implicitly set to False whenever a getter function is registered
        - otherwise, set to True whenever self.init is requested the first time.
        """
        if self._init is _NOT_SET:
            self._init = True
        return self._init

    @property
    def getter(self) -> Callable:
        return self._getter

    @getter.setter
    def getter(self, value):
        assert callable(value)

        if value.__name__ != "<lambda>":
            # If we have a proper getter, try to get the name and type of
            # the field from it.
            # If we already have the name, make sure it matches the name.

            if self.name:
                if value.__name__ != self.name:
                    raise ValueError(f"Getter {value} name should match the field name {self.name!r}")
            else:
                self.name = value.__name__

            if not self.has_type:
                if hasattr(value, "__annotations__") and "return" in value.__annotations__:
                    self.type = value.__annotations__["return"]

        if self._init is _NOT_SET:
            self._init = False

        self._getter = value

    @property
    def default_attr_name(self):
        assert self.name
        return f"_strictus#{self.name}"

    def __call__(self, getter: Callable) -> "strictus_field":
        self.getter = getter
        return self

    def __get__(self, instance: strictus, owner: Type[strictus]):
        assert self.name
        if instance is None:
            # Double check for integrity - make sure this points to the same thing
            # that the schema points to
            assert owner._strictus_schema[self.name] is self
            return self
        if self._getter:
            return self._getter(instance)
        if hasattr(instance, self.default_attr_name):
            return getattr(instance, f"_strictus#{self.name}")
        raise AttributeError(self.name)

    def __set__(self, instance: strictus, value: Any):
        assert self.name
        if self._getter:
            # A field with a getter is a virtual field,
            # so setting its value makes little sense.
            raise AttributeError(f"can't set attribute {self.name}")
        if self.read_only and not instance._strictus_initialising:
            raise AttributeError(f"can't set attribute {self.name}")

        return setattr(instance, f"_strictus#{self.name}", parse_value(field=self, raw_value=value))

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name!r}>"


def get_schema(cls_or_instance: Union[Type[strictus], strictus]) -> StrictusSchema:
    return cls_or_instance._strictus_schema


def is_strictus(anything) -> bool:
    return hasattr(anything, "_strictus_schema")


def is_strictus_container(anything) -> bool:
    raise NotImplementedError()


def parse_list(field: strictus_field, raw_value) -> List:
    assert raw_value is not None
    value = field.list_container_cls()
    for raw_item in raw_value:
        if raw_item is None:
            value.append(raw_item)
        else:
            value.append(field.item_type(raw_item))
    return value


def parse_dict(field: strictus_field, raw_value) -> Dict:
    assert raw_value is not None
    value = field.dict_container_cls()
    for item_key, raw_item_value in raw_value.items():
        if raw_item_value is None:
            value[item_key] = None
        else:
            value[item_key] = field.item_type(raw_item_value)
    return value


def parse_value(field: strictus_field, raw_value) -> Any:
    if raw_value is None or field.type is Any:
        return raw_value
    elif field.is_strictus:
        return field.type(raw_value)
    elif field.is_strictus_container:
        if field.is_list:
            return parse_list(field=field, raw_value=raw_value)
        elif field.is_dict:
            return parse_dict(field=field, raw_value=raw_value)
        else:
            raise NotImplementedError()
    elif field.type in (bool, int, float, str):
        return field.type(raw_value)
    elif field.is_list and field.item_type in (bool, int, float, str):
        return parse_list(field=field, raw_value=raw_value)
    elif field.is_dict and field.item_type in (bool, int, float, str):
        return parse_dict(field=field, raw_value=raw_value)

    return raw_value
