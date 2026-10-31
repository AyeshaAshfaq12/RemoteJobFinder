import "@rjf/ui/tokens.css";
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Remote Job Finder",
  description: "Real remote jobs you can actually take, a ghost-job filter, and honest tailored CVs — inside Claude.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
