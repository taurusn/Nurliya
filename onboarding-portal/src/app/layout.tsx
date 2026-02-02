import type { Metadata } from 'next'
import { AuthProvider } from '@/lib/auth'
import './globals.css'

export const metadata: Metadata = {
  title: 'Nurliya Onboarding Portal',
  description: 'Internal portal for taxonomy review and approval',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
