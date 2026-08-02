"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { KeyRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { passwordResetError } from "@/lib/auth-validation"
import { createClient } from "@/lib/supabase/client"

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [checking, setChecking] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()
  const [supabase] = useState(() => createClient())

  useEffect(() => {
    let active = true
    supabase.auth.getUser().then(({ data }) => {
      if (!active) return
      if (!data.user) setError("This password reset link is invalid or has expired.")
      setChecking(false)
    })
    return () => { active = false }
  }, [supabase])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const validationError = passwordResetError(password, confirmation)
    if (validationError) {
      setError(validationError)
      return
    }

    setLoading(true)
    setError(null)
    const { error: updateError } = await supabase.auth.updateUser({ password })
    if (updateError) {
      setError(updateError.message)
      setLoading(false)
      return
    }

    await supabase.auth.signOut()
    router.replace("/login")
  }

  const disabled = checking || loading || Boolean(error?.includes("invalid or has expired"))

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mb-2 flex justify-center">
            <div className="rounded-lg bg-primary/10 p-3">
              <KeyRound aria-hidden="true" className="h-8 w-8 text-primary" />
            </div>
          </div>
          <h1 className="text-xl font-semibold leading-none tracking-tight">Choose a new password</h1>
          <CardDescription>Use at least 6 characters.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                name="new-password"
                type="password"
                autoComplete="new-password"
                minLength={6}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm password</Label>
              <Input
                id="confirm-password"
                name="confirm-password"
                type="password"
                autoComplete="new-password"
                minLength={6}
                required
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                disabled={disabled}
              />
            </div>
            {error && <p role="alert" aria-live="polite" className="text-sm text-destructive">{error}</p>}
            <Button className="w-full" type="submit" disabled={disabled}>
              {checking ? "Checking link..." : loading ? "Updating..." : "Update password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
