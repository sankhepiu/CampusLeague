"""Input limits shared by every app's serializers.

ASSUMPTION (the plan gives no limits): upper bounds that keep stored values
sensible and stop a typo (or an attack) from putting an absurd number in the
ledger. Each one is enforced by a serializer and listed in the API contract.
"""
import re

from django.core.validators import RegexValidator

# Rs 1 crore, in paise. The cap for any single price, budget, goal, expense
# or sale.
MAX_AMOUNT = 1_000_000_000
MAX_CAPACITY = 100_000
MAX_TITLE = 200
MAX_DESCRIPTION = 2000

# College ids look like "SSA-001": letters, digits and hyphens, 3 to 20
# characters, starting and ending with a letter or digit.
COLLEGE_ID_PATTERN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{1,18})[A-Za-z0-9]$')
college_id_validator = RegexValidator(
    COLLEGE_ID_PATTERN,
    'Use 3 to 20 letters, digits or hyphens, for example SSA-001.',
    code='invalid_college_id',
)
