import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Moat",
  description: "SEC filing research assistant",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-white text-neutral-900">
        {children}
      </body>
    </html>
  );
}
