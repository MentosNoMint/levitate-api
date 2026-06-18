import type { Metadata } from "next";
import AppBootstrap from "@/components/AppBootstrap";
import "./globals.css";

export const metadata: Metadata = {
  title: "Levitate API Dashboard",
  description: "OpenAI-compatible proxy gateway with automatic rotation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AppBootstrap>{children}</AppBootstrap>
      </body>
    </html>
  );
}
