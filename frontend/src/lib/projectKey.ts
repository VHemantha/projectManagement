/** The full first word of the name, as typed: "Pochin Group" -> "Pochin". Letters/digits
 * only; leading digits are dropped and very short first words are joined with the next
 * ("A Team" -> "ATeam", "2026 Accounts" -> "Accounts"). */
export function suggestKey(name: string) {
  const words = name
    .trim()
    .split(/\s+/)
    .map((w) => w.replace(/[^A-Za-z0-9]/g, ''))
    .filter(Boolean)
  // Keys start with a letter, so leading digits never count towards the minimum length.
  let key = ''
  for (const word of words) {
    key = (key + word).replace(/^[0-9]+/, '')
    if (key.length >= 2) break
  }
  return key.slice(0, 100)
}
