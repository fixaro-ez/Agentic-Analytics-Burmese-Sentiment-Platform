export function validateEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export function passwordResetError(password: string, confirmation: string): string | null {
  if (password.length < 6) return "Password must be at least 6 characters"
  if (password !== confirmation) return "Passwords do not match"
  return null
}
