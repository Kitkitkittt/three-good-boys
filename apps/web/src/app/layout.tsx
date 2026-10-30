import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "LifeMate runs",
  description: "Team dashboard for permitted experiment runs.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>
          <nav>
            <Link href="/">Runs</Link>
            <Link href="/runs/new">New run</Link>
            <Link href="/compare">Compare</Link>
          </nav>
          {children}
        </main>
      </body>
    </html>
  );
}
