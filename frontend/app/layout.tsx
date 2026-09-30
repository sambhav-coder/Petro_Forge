import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PETROFORGE — Physics × AI — Digital Twin",
  description:
    "PetroForge: Premium industrial digital twin platform for well-to-surface optimization of Cyclic Steam Stimulation and SRP operations in heavy oil reservoirs.",
  keywords: [
    "digital twin",
    "oil and gas",
    "cyclic steam stimulation",
    "CSS",
    "SRP",
    "sucker rod pump",
    "heavy oil",
    "reservoir optimization",
    "physics simulation",
    "AI forecasting",
  ],
  authors: [{ name: "PetroForge" }],
  icons: {
    icon: "/icon.svg",
  },
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 5,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-oil-black text-cream-soft antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
