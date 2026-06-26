import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import AppBootstrap from "@/components/AppBootstrap";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "cyrillic"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin", "cyrillic"],
});

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
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="antialiased">
        <AppBootstrap>{children}</AppBootstrap>
      </body>
    </html>
  );
}
