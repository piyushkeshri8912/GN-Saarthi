import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";
import AppInitializer from "../components/layout/AppInitializer";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "GN Saarthi",
  description: "RAG chatbot for IIT Gandhinagar.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full overflow-hidden">
      <body
        className={`${inter.variable} ${outfit.variable} font-sans bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100 antialiased h-full overflow-hidden w-full`}
      >
        <AppInitializer>{children}</AppInitializer>
      </body>
    </html>
  );
}
