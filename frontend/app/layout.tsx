import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Platform Walkthrough Agent",
  description:
    "An agent that runs a live product demo in a real browser and answers questions mid-flight.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
