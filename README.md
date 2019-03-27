# strictus

A much tested rewrite of [strictus-dictus][1] ([github repo][2]) which does not extend `dict`.

### Installation

```bash
pip install strictus
```

### Usage

```python
from typing import List

from strictus.core import strictus, strictus_field


class Item(strictus):
    id: str
    name: str


class ItemList(strictus):
    items: List[Item] = strictus_field(default_factory=list)


item_list = ItemList({"items": [{"id": 1, "name": "first"}]})
print(item_list.items[0].name)  # prints "first"
print(item_list.to_dict())  # prints "{'items': [{'id': '1', 'name': 'first'}]}"

```

[1]: https://pypi.org/project/strictus-dictus/
[2]: https://github.com/jbasko/strictus-dictus
