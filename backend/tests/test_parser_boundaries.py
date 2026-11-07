import json

import pytest

from nova_backend.parsing import ReportValidationError, modifiers


@pytest.mark.parametrize("field", ["price", "quantity", "id", "name"])
def test_empty_required_modifier_fields_are_rejected(field):
    modifier = {"name": "Extra chicken", "id": "M01", "price": 1, "quantity": 1}
    modifier[field] = ""
    with pytest.raises(ReportValidationError):
        modifiers(json.dumps([modifier]))
