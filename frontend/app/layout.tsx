import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PetroForge — 3D Digital Twin (SIH26120)",
  description:
    "Physics + AI Digital Twin for well-to-surface optimization of CSS and SRP operations in heavy oil wells.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#070b14] font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
