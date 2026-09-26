/** "+79135551234" as "+7 913 555-12-34"; anything else is shown as stored. */
export function formatPhone(phone: string): string {
  const match = phone.match(/^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/);
  return match ? `+7 ${match[1]} ${match[2]}-${match[3]}-${match[4]}` : phone;
}
