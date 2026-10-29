import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Receivables Registry",
  description: "Check receivables for duplicated or inconsistent invoices before they are financed twice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
