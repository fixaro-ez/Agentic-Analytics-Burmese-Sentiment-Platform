import assert from "node:assert/strict"
import test from "node:test"

import { passwordResetError, validateEmail } from "./auth-validation.ts"

test("email validation rejects malformed addresses", () => {
  assert.equal(validateEmail("person@example.com"), true)
  assert.equal(validateEmail("person@localhost"), false)
  assert.equal(validateEmail("not an email"), false)
})

test("password reset validation enforces length and confirmation", () => {
  assert.equal(passwordResetError("short", "short"), "Password must be at least 6 characters")
  assert.equal(passwordResetError("long-enough", "different"), "Passwords do not match")
  assert.equal(passwordResetError("long-enough", "long-enough"), null)
})
