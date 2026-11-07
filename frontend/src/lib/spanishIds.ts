/**
 * Spanish tax identifiers, mirroring the server-side rules (`app/invoicing/spanish_ids.py`)
 * so that the forms can explain a problem before submitting.
 */

const NIF_CONTROL = 'TRWAGMYFPDXBNJZSQVHLCKE'
const NIE_PREFIXES = 'XYZ'
const CIF_LETTERS = 'ABCDEFGHJNPQRSUVW'
const CIF_LETTER_CONTROL = 'JABCDEFGHI'
const CIF_CONTROL_IS_LETTER = 'KPQSNW'
const CIF_CONTROL_IS_DIGIT = 'ABEH'

/** Upper-case, without the blanks, dots or hyphens people type in. */
export function normaliseId(value: string): string {
  return value.replace(/[\s.-]/g, '').toUpperCase()
}

/** A well-formed DNI (8 digits + letter) or NIE (X/Y/Z + 7 digits + letter) with a correct letter. */
export function isValidNif(value: string): boolean {
  const id = normaliseId(value)
  const dni = /^(\d{8})([A-Z])$/.exec(id)
  if (dni) return dni[2] === NIF_CONTROL[Number(dni[1]) % 23]
  const nie = /^([XYZ])(\d{7})([A-Z])$/.exec(id)
  if (nie) return nie[3] === NIF_CONTROL[Number(`${NIE_PREFIXES.indexOf(nie[1])}${nie[2]}`) % 23]
  return false
}

/** A well-formed CIF (entity letter + 7 digits + control character) with a correct control. */
export function isValidCif(value: string): boolean {
  const match = /^([A-Z])(\d{7})([0-9A-J])$/.exec(normaliseId(value))
  if (!match || !CIF_LETTERS.includes(match[1])) return false
  const [, letter, digits, control] = match
  let sum = 0
  for (let i = 0; i < digits.length; i++) {
    const d = Number(digits[i])
    if (i % 2 === 1) sum += d
    else {
      const doubled = d * 2
      sum += Math.floor(doubled / 10) + (doubled % 10)
    }
  }
  const figure = (10 - (sum % 10)) % 10
  if (CIF_CONTROL_IS_LETTER.includes(letter)) return control === CIF_LETTER_CONTROL[figure]
  if (CIF_CONTROL_IS_DIGIT.includes(letter)) return control === String(figure)
  return control === String(figure) || control === CIF_LETTER_CONTROL[figure]
}
