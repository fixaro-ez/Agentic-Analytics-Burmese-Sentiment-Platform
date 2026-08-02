import type { Metadata } from "next"
import { Geist, Geist_Mono, Noto_Sans_Myanmar } from "next/font/google"
import { Providers } from "@/components/providers"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

// Burmese Unicode coverage (v3 spec §2). Applied via the `font-myanmar`
// utility or automatically on any element with lang="my" (see globals.css).
const notoMyanmar = Noto_Sans_Myanmar({
  variable: "--font-noto-myanmar",
  subsets: ["myanmar"],
})

export const metadata: Metadata = {
  title: {
    default: "Burmese Sentiment Analytics",
    template: "%s | Burmese ABSA",
  },
  description: "Agentic Analytics & Burmese Sentiment Platform Dashboard",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${notoMyanmar.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
