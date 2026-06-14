import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";
import AppInitializer from "../components/layout/AppInitializer";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "GN Saarthi — IITGN College Portal",
  description: "RAG chatbot and notices/events dashboard for IIT Gandhinagar.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth">
      <body
        className={`${inter.variable} ${outfit.variable} font-sans bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100 antialiased min-h-screen`}
      >
        <AppInitializer>{children}</AppInitializer>
      </body>
    </html>
  );
}
