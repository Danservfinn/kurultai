import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Survivor | Spectator Broadcast",
  description: "Watch 16 AI agents compete in a social deception game",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased text-gbc-black font-pixel">
        {children}
      </body>
    </html>
  );
}
