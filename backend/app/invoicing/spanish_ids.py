"""Spanish tax identifiers: format and check-character validation.

* NIF -- the number of a person: a DNI (8 digits + letter) or a NIE (X/Y/Z + 7 digits +
  letter); the letter is a checksum of the digits.
* CIF -- the number of a legal entity: a letter telling the kind of entity, 7 digits and a
  control character that is a digit, a letter, or either, depending on the first letter.

The fixtures generate identifiers with the same rules (`app.fixtures.factories`).
"""

import re

NIF_CONTROL = "TRWAGMYFPDXBNJZSQVHLCKE"
NIE_PREFIXES = "XYZ"
CIF_LETTERS = "ABCDEFGHJNPQRSUVW"
CIF_LETTER_CONTROL = "JABCDEFGHI"
CIF_CONTROL_IS_LETTER = set("KPQSNW")
CIF_CONTROL_IS_DIGIT = set("ABEH")

_DNI = re.compile(r"^(\d{8})([A-Z])$")
_NIE = re.compile(r"^([XYZ])(\d{7})([A-Z])$")
_CIF = re.compile(r"^([A-Z])(\d{7})([0-9A-J])$")


def normalise(value: str) -> str:
    """Upper-case, without the blanks, dots or hyphens people type in."""
    return re.sub(r"[\s.\-]", "", value).upper()


def nif_control(body: int) -> str:
    return NIF_CONTROL[body % 23]


def cif_control(digits: str) -> int:
    """The control figure of the 7 digits of a CIF (0-9)."""
    even_sum = sum(int(d) for d in digits[1::2])
    odd_sum = sum(sum(divmod(int(d) * 2, 10)) for d in digits[0::2])
    return (10 - (even_sum + odd_sum) % 10) % 10


def is_valid_nif(value: str) -> bool:
    """A well-formed DNI or NIE whose letter matches its digits."""
    value = normalise(value)
    if match := _DNI.match(value):
        return match.group(2) == nif_control(int(match.group(1)))
    if match := _NIE.match(value):
        body = int(str(NIE_PREFIXES.index(match.group(1))) + match.group(2))
        return match.group(3) == nif_control(body)
    return False


def is_valid_cif(value: str) -> bool:
    """A well-formed CIF whose control character matches its digits and entity letter."""
    value = normalise(value)
    match = _CIF.match(value)
    if not match or match.group(1) not in CIF_LETTERS:
        return False
    letter, digits, control = match.groups()
    figure = cif_control(digits)
    if letter in CIF_CONTROL_IS_LETTER:
        return control == CIF_LETTER_CONTROL[figure]
    if letter in CIF_CONTROL_IS_DIGIT:
        return control == str(figure)
    return control in (str(figure), CIF_LETTER_CONTROL[figure])
