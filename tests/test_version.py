# pylint: disable=missing-function-docstring

### IMPORTS
### ============================================================================
## Standard Library
import datetime

## Installed

## Application
from dcdc import _version


### TESTS
### ============================================================================
def test_build_datetime_type():
    assert isinstance(_version.BUILD_DATETIME, datetime.datetime)
